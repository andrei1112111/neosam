import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.fernet import Fernet

class I2PSecureChannel:
    def __init__(self, chat_name: str):
        self.chat_name = chat_name

        # Генерируем асимметричную пару ключей для нового чата chat_name
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        self.shared_cipher = None

    def get_handshake_package(self):
        """Возвращает публичный ключ для передачи по защещенному каналу"""
        pub_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return base64.b64encode(pub_bytes).decode()

    def finalize_handshake(self, friend_pub_str: str):
        """Принимает публичный ключ и создает общий ключ"""
        friend_pub_bytes = base64.b64decode(friend_pub_str)
        friend_public_key = serialization.load_pem_public_key(friend_pub_bytes)
        
        # Вычисляем общий секрет (Diffie-Hellman)
        shared_secret = self.private_key.exchange(ec.ECDH(), friend_public_key)
        
        # Превращаем секрет в ключ для Fernet через KDF
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.chat_name.encode(), # Имя чата как соль
            info=b'i2p-secure-session',
        ).derive(shared_secret)
        
        self.shared_cipher = Fernet(base64.urlsafe_b64encode(derived_key))

    def encrypt(self, message: str) -> str:
        if not self.shared_cipher:
            raise Exception("Шифрование не настроено!")
        return self.shared_cipher.encrypt(message.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        if not self.shared_cipher:
            raise Exception("Шифрование не настроено!")
        return self.shared_cipher.decrypt(encrypted_data.encode()).decode()

# --- Симуляция процесса ---

# 1. User1 создает чат
user1 = I2PSecureChannel("SecretChat#1")
key_for_flash_drive = user1.get_handshake_package()
print(f"User1 сохранил на флешку: {key_for_flash_drive[:30]}...")

# 2. User2 получает флешку и создает свой объект
user2 = I2PSecureChannel("SecretChat#1")
print(key_for_flash_drive)
key_for_flash_drive = f"A{key_for_flash_drive[1:]}"
print(key_for_flash_drive)
user2.finalize_handshake(key_for_flash_drive) # Ввел ключ с флешки

# 3. Теперь User2 должен отправить СВОЙ ключ обратно User1 (уже по сети I2P)
key_back_via_network = user2.get_handshake_package()

# 4. User1 получает ключ по сети и завершает настройку
user1.finalize_handshake(key_back_via_network)

# --- ПРОВЕРКА ОБМЕНА ---

# User1 отправляет сообщение
msg_from_1 = user1.encrypt("Привет, это зашифровано через DH!")
print(f"\nПо сети I2P летит это: {msg_from_1}")

# User2 расшифровывает
decrypted_by_2 = user2.decrypt(msg_from_1)
print(f"User2 прочитал: {decrypted_by_2}")

# User2 отвечает
msg_from_2 = user2.encrypt("Вижу тебя громко и ясно!")
print(f"User1 получил ответ: {user1.decrypt(msg_from_2)}")
