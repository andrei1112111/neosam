from ui import CMD_UI


# import socket

# # Проверяем именно SAM порт из вашего конфига
# def test_sam():
#     try:
#         with socket.create_connection(('127.0.0.1', 7656), timeout=5) as s:
#             s.sendall(b'HELLO VERSION MIN=3.1 MAX=3.1\n')
#             data = s.recv(1024).decode()
#             print(f"Ответ от SAM: {data.strip()}")
#             if "OK" in data:
#                 print("✅ SAM готов к работе. Вы можете создавать туннели.")
#     except Exception as e:
#         print(f"❌ SAM не отвечает: {e}")

# test_sam()


if __name__ == "__main__":
    CMD_UI().run()
