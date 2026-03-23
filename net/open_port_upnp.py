try:
    import miniupnpc
except ModuleNotFoundError:
    miniupnpc = None

def open_port(port, protocol='TCP', description='i2pd port'):
    return
    if miniupnpc is None:
        return "Ошибка: miniupnpc не установлен."

    upnp = miniupnpc.UPnP()
    
    # Увеличиваем время ожидания ответа от роутера
    upnp.discoverdelay = 200 
    
    try:
        # Пытаемся найти устройства
        devices = upnp.discover()
        print(f"Найдено устройств: {devices}")
        
        # Выбираем IGD (Internet Gateway Device)
        upnp.selectigd()
        
        # Получаем внешний IP (проверка связи с роутером)
        ext_ip = upnp.externalipaddress()
        print(f"Ваш внешний IP: {ext_ip}")
        
        # Пробрасываем порт
        # addportmapping(external_port, protocol, internal_client, internal_port, description, remote_host)
        res = upnp.addportmapping(
            port, protocol, upnp.lanaddr, port, description, ''
        )
        return "Порт успешно открыт!" if res else "Роутер отклонил запрос."
        
    except Exception as e:
        # Если вылетает 'Success', пробуем игнорировать и идти дальше
        if "Success" in str(e) or not str(e):
             return "Произошла странная ошибка macOS, но попробуйте проверить статус в i2pd."
        return f"Ошибка: {e}"


def force_close(port):
    return
    upnp = miniupnpc.UPnP()
    upnp.discoverdelay = 500
    try:
        upnp.discover()
        upnp.selectigd()
        
        # Пробуем удалить и TCP, и UDP (на всякий случай)
        for proto in ['TCP', 'UDP']:
            try:
                res = upnp.deleteportmapping(port, proto)
                print(f"Порт {port}/{proto}: {'Удален' if res else 'Уже отсутствует'}")
            except Exception:
                print(f"Порт {port}/{proto}: Не найден в таблице роутера.")
                
    except Exception as e:
        print(f"Общая ошибка связи с роутером: {e}")

# Список портов, которые мы "наследили"
ports_to_clean = [44444, 7656]
for p in ports_to_clean:
    force_close(p)
