try:
    import miniupnpc
except ModuleNotFoundError:
    miniupnpc = None

def open_port(port, protocol='TCP', description='i2pd port'):
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
