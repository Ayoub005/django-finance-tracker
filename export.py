import sqlite3

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()
boolean_columns = ['is_superuser', 'is_staff', 'is_active', 'is_deleted']

def generate_users_force():
    cursor.execute("PRAGMA table_info(auth_user)")
    columns = [row[1] for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM auth_user")
    with open('import_users_force.sql', 'w', encoding='utf-8') as f:
        for row in cursor.fetchall():
            values = []
            for idx, val in enumerate(row):
                col_name = columns[idx]
                if val is None:
                    values.append("NULL")
                elif col_name in boolean_columns:
                    values.append("TRUE" if val else "FALSE")
                elif isinstance(val, (int, float)):
                    values.append(str(val))
                else:
                    val = str(val).replace("'", "''")
                    values.append(f"'{val}'")
                    
            col_str = ", ".join(columns)
            val_str = ", ".join(values)
            
            # This tells PostgreSQL to force-overwrite the Super-User data with Ayoub's data
            update_str = ", ".join([f"{col}=EXCLUDED.{col}" for col in columns if col != 'id'])
            f.write(f"INSERT INTO auth_user ({col_str}) VALUES ({val_str}) ON CONFLICT (id) DO UPDATE SET {update_str};\n")

generate_users_force()
print("Success: import_users_force.sql generated!")