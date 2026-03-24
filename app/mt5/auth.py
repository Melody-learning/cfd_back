"""MT5 Web API MD5 双向认证算法"""
import hashlib
import os


def compute_srv_rand_answer(password: str, srv_rand_hex: str) -> str:
    """
    计算发送给 MT5 服务器的 srv_rand_answer。

    算法步骤:
        1. MD5(密码的 UTF-16-LE 编码)
        2. MD5(步骤1结果 + 'WebAPI' ASCII)
        3. MD5(步骤2结果 + srv_rand 字节)

    Args:
        password: Manager 密码明文
        srv_rand_hex: 服务器返回的 16 字节随机数(hex 字符串)

    Returns:
        srv_rand_answer 的 hex 字符串
    """
    # 步骤 1: MD5(密码 UTF-16-LE)
    pass_utf16 = password.encode("utf-16-le")
    pass_md5 = hashlib.md5(pass_utf16).digest()

    # 步骤 2: MD5(步骤1 + 'WebAPI')
    password_hash = hashlib.md5(pass_md5 + b"WebAPI").digest()

    # 步骤 3: MD5(步骤2 + srv_rand 字节)
    srv_rand_bytes = bytes.fromhex(srv_rand_hex)
    answer = hashlib.md5(password_hash + srv_rand_bytes).hexdigest()

    return answer


def generate_cli_rand() -> tuple[bytes, str]:
    """
    生成客户端随机序列（16 字节）。

    Returns:
        (cli_rand_bytes, cli_rand_hex) — 字节和 hex 形式
    """
    cli_rand_bytes = os.urandom(16)
    cli_rand_hex = cli_rand_bytes.hex()
    return cli_rand_bytes, cli_rand_hex


def verify_cli_rand_answer(
    password: str, cli_rand_bytes: bytes, cli_rand_answer_hex: str
) -> bool:
    """
    验证 MT5 服务器返回的 cli_rand_answer，确认服务器身份。

    算法: cli_rand_answer = MD5(password_hash + cli_rand_bytes)
    其中 password_hash = MD5(MD5(password UTF-16-LE) + 'WebAPI')

    Args:
        password: Manager 密码明文
        cli_rand_bytes: 客户端生成的随机字节
        cli_rand_answer_hex: 服务器返回的应答(hex 字符串)

    Returns:
        True 如果服务器身份验证通过
    """
    pass_utf16 = password.encode("utf-16-le")
    pass_md5 = hashlib.md5(pass_utf16).digest()
    password_hash = hashlib.md5(pass_md5 + b"WebAPI").digest()

    expected = hashlib.md5(password_hash + cli_rand_bytes).hexdigest()
    return expected == cli_rand_answer_hex
