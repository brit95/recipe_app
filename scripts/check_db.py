import os
import sqlite3

home = os.path.expanduser('~')
home_db = os.path.join(home, '.recipe_manager.db')
print('HOME_DIR', home)
if os.path.exists(home_db):
    try:
        conn = sqlite3.connect(home_db)
        rows = conn.execute('SELECT id,name FROM recipes ORDER BY id').fetchall()
        print('HOME_DB', home_db, 'COUNT', len(rows))
        for r in rows:
            print(r[0], '\t', r[1])
        conn.close()
    except Exception as e:
        print('ERROR_OPENING_HOME_DB', e)
else:
    print('HOME_DB_NOT_FOUND', home_db)

repo = r'c:/git/claude/brit/recipe_app'
found = []
for root, dirs, files in os.walk(repo):
    for f in files:
        if f.endswith('.db') or f == '.recipe_manager.db':
            found.append(os.path.join(root, f))

print('FOUND_DB_FILES', len(found))
for p in found:
    print('-', p)
    try:
        conn = sqlite3.connect(p)
        cnt = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        print('  tables=', cnt)
        try:
            rc = conn.execute('SELECT count(*) FROM recipes').fetchone()[0]
            print('  recipes=', rc)
        except Exception as e:
            print('  recipes: error', e)
        conn.close()
    except Exception as e:
        print('  open error', e)
