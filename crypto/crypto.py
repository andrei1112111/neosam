import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.fernet import Fernet
import secrets


class SecureChannel:
    """
    1. Cоздайте SecureChannel("уникальный идентификатор чата")
    2. Cделайте .get_handshake_package() и передайте полученные данные по доверенному каналу.
    3. Второй юзер делает .finalize_handshake("полученные вами данные") 
    4 Вы меняетесь ролями и повтроряете шаги 2 и 3.

    Готово!

    - msg = "hey"
    - user1.encrypt(msg)
    - print(user2.decrypt(msg))  # hey
    """
    def __init__(self):
        # Генерируем асимметричную пару ключей для нового чата chat_name
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        self.shared_cipher = None
        self.my_salt = secrets.token_bytes(32)

    def get_handshake_package(self):
        """Возвращает данные для передачи по защещенному каналу"""
        pub_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return {
            "salt": base64.b64encode(self.my_salt).decode(),
            "pkey": base64.b64encode(pub_bytes).decode()
        }
    
    def finalize_handshake(self, friend_pub_package: dict):
        """Принимает публичный ключ и создает общий ключ"""
        friend_pub_bytes = base64.b64decode(friend_pub_package["pkey"])
        friend_salt = base64.b64decode(friend_pub_package["salt"])

        friend_public_key = serialization.load_pem_public_key(friend_pub_bytes)
        
        # Вычисляем общий секрет (Diffie-Hellman)
        shared_secret = self.private_key.exchange(ec.ECDH(), friend_public_key)
        
        # Превращаем секрет в ключ для Fernet через KDF
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=friend_salt, # Имя чата как соль
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
