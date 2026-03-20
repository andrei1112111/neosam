import asyncio
import sys

class I2PConnection():
    def __init__(self) -> None:
        pass

async def sam_handshake(reader, writer):
    # Приветствие SAM
    writer.write(b"HELLO VERSION MIN=3.1 MAX=3.1\n")
    await writer.drain()
    line = await reader.readline()
    if b"RESULT=OK" not in line:
        raise Exception("SAM handshake failed")

    # Создаем сессию (она должна оставаться открытой!)
    writer.write(b"SESSION CREATE STYLE=STREAM ID=mysess DESTINATION=TRANSIENT\n")
    await writer.drain()
    line = await reader.readline()
    
    parts = line.decode().split(" ")
    dest_part = [p for p in parts if p.startswith("DESTINATION=")][0]
    my_dest = dest_part.replace("DESTINATION=", "").strip()
    return my_dest

async def listen_for_messages():
    """Фоновая задача для приема входящих соединений"""
    while True:
        try:
            # Для каждого ACCEPT нужно новое служебное соединение с SAM
            reader, writer = await asyncio.open_connection('127.0.0.1', 7656)
            
            writer.write(b"HELLO VERSION MIN=3.1 MAX=3.1\n")
            await writer.drain()
            await reader.readline()

            # Подписываемся на входящие для существующей сессии mysess
            writer.write(b"STREAM ACCEPT ID=mysess\n")
            await writer.drain()
            
            line = await reader.readline()
            if b"RESULT=OK" in line:
                # ВАЖНО: SAM присылает Base64 адрес отправителя первой строкой
                await reader.readline() 
                
                # Читаем само сообщение
                data = await reader.read(4096)
                if data:
                    print(f"\n[Собеседник]: {data.decode().strip()}")
                    print("Вы: ", end="", flush=True)
            
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            # Небольшая пауза при ошибке, чтобы не заспамить лог
            await asyncio.sleep(2)

async def run_messenger():
    # Сохраняем ссылки на объекты, чтобы они не закрылись
    session_reader = None
    session_writer = None
    listen_task = None
    
    try:
        # 1. Создаем основное соединение сессии (оно должно жить ВЕСЬ сеанс)
        session_reader, session_writer = await asyncio.open_connection('127.0.0.1', 7656)
        my_dest = await sam_handshake(session_reader, session_writer)
        
        print(f"\n[*] ВАШ I2P АДРЕС:\n{my_dest}\n")
        print("[!] Скопируйте этот адрес и отправьте другу.")
        
        friend_dest = ""
        while not friend_dest:
            # Используем run_in_executor для input, чтобы не блокировать event loop
            print("ВВЕДИТЕ АДРЕС ДРУГА ДЛЯ НАЧАЛА ЧАТА: ", end="", flush=True)
            friend_dest = (await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)).strip()

        print("\n[+] ЧАТ СОЗДАН. Пишите сообщения ниже.")
        print("(Доставка в I2P занимает время, подождите 10-15 сек)\n")

        # 2. Запускаем фоновое прослушивание и СОХРАНЯЕМ ссылку
        listen_task = asyncio.create_task(listen_for_messages())

        # 3. Цикл отправки
        while True:
            print("Вы: ", end="", flush=True)
            msg = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            msg = msg.strip()
            
            if msg.lower() == 'exit': 
                break
            if not msg: 
                continue

            try:
                s_reader, s_writer = await asyncio.open_connection('127.0.0.1', 7656)
                s_writer.write(b"HELLO VERSION MIN=3.1 MAX=3.1\n")
                await s_writer.drain()
                await s_reader.readline()

                cmd = f"STREAM CONNECT ID=mysess DESTINATION={friend_dest} SILENT=false\n"
                s_writer.write(cmd.encode())
                await s_writer.drain()
                
                resp = await s_reader.readline()
                if b"RESULT=OK" in resp:
                    s_writer.write(msg.encode() + b"\n")
                    await s_writer.drain()
                    print("[+] Отправлено")
                else:
                    print(f"[!] Ошибка: Собеседник недоступен (строит туннели).")
                
                s_writer.close()
                await s_writer.wait_closed()
            except Exception as e:
                print(f"[!] Ошибка сети при отправке: {e}")

    except Exception as e:
        print(f"[!] Критическая ошибка: {e}")
    finally:
        if listen_task:
            listen_task.cancel()
        if session_writer:
            session_writer.close()
            await session_writer.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(run_messenger())
    except KeyboardInterrupt:
        print("\n[*] Выход...")
