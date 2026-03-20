import sqlite3
conn = sqlite3.connect('backend/data/local_data.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print('Tables:', [r[0] for r in cur.fetchall()])
conn.close()
