"""Xác thực tạm cho môi trường phát triển.

KHÔNG dùng với dữ liệu thật: Sprint 1 thay bằng Keycloak, MFA và phân quyền 4 vai trò (SEC 01).
"""
from dataclasses import dataclass

from fastapi import Header

from .errors import ApiError


@dataclass
class User:
    name: str
    client_ids: set[str]


def current_user(x_user: str | None = Header(None), x_client_ids: str = Header("")) -> User:
    if not x_user:
        raise ApiError("unauthenticated")
    return User(x_user, {c.strip() for c in x_client_ids.split(",") if c.strip()})


def require_scope(user: User, client_id: str) -> None:
    if client_id not in user.client_ids:
        # 404 để không tiết lộ sự tồn tại của dữ liệu khách hàng khác
        raise ApiError("not_found")
