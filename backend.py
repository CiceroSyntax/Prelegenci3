from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import re

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Database setup - Railway friendly
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "prelegenci.db")

def get_db_connection():
    """Tworzy połączenie z bazą danych"""
    db_abs = os.path.abspath(DATABASE_PATH)
    conn = sqlite3.connect(db_abs)
    conn.row_factory = sqlite3.Row
    return conn

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# --------- FRONTEND - SERWOWANIE PLIKÓW ---------
@app.route('/')
def index():
    """Serwuje główną stronę HTML"""
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    """Serwuje statyczne pliki (CSS, JS, obrazy)"""
    return send_from_directory('.', filename)

# --------- ENDPOINTY API ---------

@app.route('/api/speakers/search', methods=['POST', 'OPTIONS'])
def search_speakers():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.get_json() or {}
        search_query = (data.get('query') or '').lower()
        filters = data.get('filters') or []

        conn = get_db_connection()
        cur = conn.cursor()

        base_query = """
            SELECT 
                id,
                prelegent,
                firma_instytucja,
                temat_prezentacji,
                problemy_wyzwania,
                mozliwosci_it_sprzedaz,
                zaczepka
            FROM prelegenci
            WHERE 1=1
        """
        params = []

        if search_query:
            base_query += """
                AND (
                    LOWER(prelegent) LIKE ? 
                    OR LOWER(firma_instytucja) LIKE ?
                    OR LOWER(temat_prezentacji) LIKE ?
                    OR LOWER(COALESCE(zaczepka, '')) LIKE ?
                )
            """
            like = f"%{search_query}%"
            params.extend([like, like, like, like])

        if filters:
            filters = [str(f).strip() for f in filters if str(f).strip()]
            if filters:
                placeholders = ",".join("?" for _ in filters)
                base_query += f" AND firma_instytucja IN ({placeholders}) "
                params.extend(filters)

        cur.execute(base_query, params)
        rows = cur.fetchall()
        conn.close()

        speakers = []
        for row in rows:
            zaczepka_value = row['zaczepka'] if row['zaczepka'] else ''
            
            speakers.append({
                'id': row['id'],
                'name': row['prelegent'],
                'company': row['firma_instytucja'] or 'Niezależny ekspert',
                'topic': row['temat_prezentacji'],
                'challenges': row['problemy_wyzwania'],
                'opportunities': parse_opportunities(row['mozliwosci_it_sprzedaz']),
                'zaczepka': zaczepka_value,
                'description': zaczepka_value if zaczepka_value else f"Ekspert w dziedzinie: {row['temat_prezentacji']}"
            })

        return jsonify({'success': True, 'data': speakers, 'count': len(speakers)})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/speakers/all', methods=['GET'])
def get_all_speakers():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                id,
                prelegent,
                firma_instytucja,
                temat_prezentacji,
                problemy_wyzwania,
                mozliwosci_it_sprzedaz,
                zaczepka
            FROM prelegenci
            ORDER BY prelegent
        """)
        rows = cur.fetchall()
        conn.close()

        speakers = []
        for row in rows:
            zaczepka_value = row['zaczepka'] if row['zaczepka'] else ''
            
            speakers.append({
                'id': row['id'],
                'name': row['prelegent'],
                'company': row['firma_instytucja'] or 'Niezależny ekspert',
                'topic': row['temat_prezentacji'],
                'challenges': row['problemy_wyzwania'],
                'opportunities': parse_opportunities(row['mozliwosci_it_sprzedaz']),
                'zaczepka': zaczepka_value,
                'description': zaczepka_value if zaczepka_value else f"Ekspert w dziedzinie: {row['temat_prezentacji']}"
            })

        return jsonify({'success': True, 'data': speakers, 'count': len(speakers)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# --------- NARZĘDZIA / DEBUG ---------

@app.route('/api/debug/info', methods=['GET'])
def debug_info():
    """Info o używanej bazie i licznik zaczepki"""
    try:
        db_abs = os.path.abspath(DATABASE_PATH)
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM prelegenci")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM prelegenci WHERE TRIM(COALESCE(zaczepka,'')) <> ''")
        with_hook = cur.fetchone()[0]

        samples = []
        cur.execute("""
            SELECT id, prelegent, firma_instytucja, temat_prezentacji, zaczepka
            FROM prelegenci
            WHERE TRIM(COALESCE(zaczepka,'')) <> ''
            LIMIT 3
        """)
        for r in cur.fetchall():
            samples.append({
                'id': r['id'],
                'prelegent': r['prelegent'],
                'firma': r['firma_instytucja'],
                'zaczepka': r['zaczepka'][:100] + '...' if len(r['zaczepka'] or '') > 100 else r['zaczepka']
            })

        conn.close()
        return jsonify({
            'success': True,
            'db_path_used': db_abs,
            'counts': {
                'total': total, 
                'with_nonempty_zaczepka': with_hook,
                'percentage': f"{(with_hook/total*100):.1f}%" if total > 0 else "0%"
            },
            'sample_records': samples
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/debug/sample/<int:pk>', methods=['GET'])
def debug_sample(pk: int):
    """Zwróć surowy rekord po id"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prelegenci WHERE id = ?", (pk,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({'success': False, 'error': f'Brak rekordu id={pk}'}), 404
        
        record = dict(row)
        
        zaczepka_info = {
            'has_zaczepka': bool(record.get('zaczepka')),
            'zaczepka_length': len(record.get('zaczepka', '')) if record.get('zaczepka') else 0,
            'zaczepka_preview': record.get('zaczepka', '')[:200] + '...' if len(record.get('zaczepka', '')) > 200 else record.get('zaczepka', '')
        }
        
        return jsonify({
            'success': True, 
            'row': record,
            'zaczepka_info': zaczepka_info
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/test', methods=['GET'])
def test_connection():
    """Test połączenia i struktura tabeli"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("PRAGMA table_info(prelegenci)")
        columns = cur.fetchall()
        column_names = [col[1] for col in columns]
        
        cur.execute("SELECT * FROM prelegenci LIMIT 1")
        sample = cur.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': 'API działa', 
            'db_path_used': os.path.abspath(DATABASE_PATH),
            'table_columns': column_names,
            'sample_record_keys': list(dict(sample).keys()) if sample else None
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# --------- POMOCNICZE ---------

def parse_opportunities(opportunities_text):
    if not opportunities_text:
        return ["Konsulting IT", "Wdrożenia systemowe", "Rozwój oprogramowania"]
    parts = re.split(r'[,;\n]', str(opportunities_text))
    parts = [p.strip() for p in parts if p and p.strip()]
    return parts[:5] if parts else ["Konsulting IT", "Wdrożenia systemowe"]

# --------- URUCHOM ---------

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0'
    
    print("🚀 Serwer startuje...")
    print(f"🌐 Host: {host}:{port}")
    print("📡 Dostępne endpointy:")
    print("   GET  / - główna strona aplikacji (index.html)")
    print("   POST /api/speakers/search - wyszukiwanie")
    print("   GET  /api/speakers/all - wszyscy prelegenci")
    print("   GET  /api/debug/info - diagnostyka bazy")
    print("   GET  /api/test - test połączenia")
    print(f"📊 Database: {os.path.abspath(DATABASE_PATH)}")

    app.run(debug=False, port=port, host=host)