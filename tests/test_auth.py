"""Tests del sistema de autenticación web."""
from web.auth import AuthManager, MAX_LOGIN_ATTEMPTS


def test_auth_system():
    am = AuthManager()

    # Test 1: Generar código
    code = am.generate_code()
    assert len(code) == 6
    assert code.isdigit()
    print(f"Código generado: {code}")

    # Test 2: Validar código correcto
    assert am.validate_code(code) is True

    # Test 3: Código ya usado (un solo uso)
    assert am.validate_code(code) is False

    # Test 4: Código inválido
    assert am.validate_code("999999") is False

    # Test 5: Generar nuevo código invalida el anterior
    code1 = am.generate_code()
    code2 = am.generate_code()
    assert am.validate_code(code1) is False
    assert am.validate_code(code2) is True

    # Test 6: Sesiones
    session = am.create_session()
    assert am.validate_session(session.token) is True

    # Test 7: Revocar sesión
    am.revoke_session(session.token)
    assert am.validate_session(session.token) is False

    # Test 8: Sesión inválida
    assert am.validate_session("token_falso") is False
    assert am.validate_session(None) is False

    # Test 9: Rate-limiting
    am2 = AuthManager()
    test_ip = "1.2.3.4"
    assert am2.is_ip_blocked(test_ip) is False
    for _ in range(MAX_LOGIN_ATTEMPTS):
        am2.record_login_attempt(test_ip)
    assert am2.is_ip_blocked(test_ip) is True
    mins = am2.get_remaining_lockout(test_ip)
    assert mins > 0

    # Test 10: Limpiar intentos tras login exitoso
    am2.clear_login_attempts(test_ip)
    assert am2.is_ip_blocked(test_ip) is False

    # Test 11: Otra IP no está bloqueada
    assert am2.is_ip_blocked("5.6.7.8") is False

    print("Todos los tests pasaron correctamente")


if __name__ == "__main__":
    test_auth_system()
