import sqlite3

con = sqlite3.connect("script_analyser.db")
con.row_factory = sqlite3.Row

print("USERS")
for r in con.execute("SELECT id, email, full_name FROM users"):
    print(dict(r))

print("\nPROJECT OWNERSHIP")
for r in con.execute("SELECT id, title, user_id FROM projects"):
    print(dict(r))

con.close()
