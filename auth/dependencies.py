from fastapi import Header, HTTPException
from auth.jwt_manager import validar_token

def verificar_token(authorization: str = Header(None)):

    #print("HEADER AUTH:", authorization)   # ← DEBUG

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="No se envió Authorization header"
        )

    auth_value = authorization.strip()

    if " " in auth_value:
        scheme, token = auth_value.split(" ", 1)
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Authorization debe usar esquema Bearer"
            )
        token = token.strip()
    else:
        # Soporte de compatibilidad para clientes que envían solo el token.
        token = auth_value

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Token vacío en Authorization"
        )

    payload = validar_token(token)

    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Token inválido"
        )

    return payload