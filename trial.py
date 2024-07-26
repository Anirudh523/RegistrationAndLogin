import mysql.connector
from mysql.connector import Error

try:
    connection = mysql.connector.connect(
        host='localhost',
        user='root',
        password='Doddhuduga1$',
        database='anislogin'
    )
    if connection.is_connected():
        print("Connection successful")
except Error as e:
    print(f"Error: {e}")
finally:
    if connection.is_connected():
        connection.close()