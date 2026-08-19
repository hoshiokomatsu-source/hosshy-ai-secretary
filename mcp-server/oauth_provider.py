"""ホッシーくん用の簡易OAuthプロバイダー

このサーバーはホシさん一人だけが使う前提のため、ログイン画面や
パスワードチェックは行わず、認可リクエストが来たら即座に承認する
「オートアプルーブ」方式にしている。

Claude.ai / Claude Desktop の「カスタムコネクタ」機能はOAuth 2.1 +
Dynamic Client Registration (DCR) を前提にしているため、これを実装
しないとコネクタ登録自体が失敗する。
"""

import json
import os
import secrets
import time
from pathlib import Path

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

ACCESS_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30  # 30日（個人利用なので長めに設定）
STATE_PATH = Path(os.path.expanduser("~/.config/hosshy/oauth_state.json"))


class SingleUserOAuthProvider(OAuthAuthorizationServerProvider):
    """認可を求められたら常に許可する、一人用の簡易OAuthプロバイダー。"""

    def __init__(self) -> None:
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.auth_codes: dict[str, AuthorizationCode] = {}
        self.access_tokens: dict[str, AccessToken] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except Exception as e:
            print(f"[oauth] 保存データの読み込みに失敗: {e}")
            return
        for item in raw.get("clients", []):
            client = OAuthClientInformationFull.model_validate(item)
            if client.client_id:
                self.clients[client.client_id] = client
        for item in raw.get("access_tokens", []):
            tok = AccessToken.model_validate(item)
            self.access_tokens[tok.token] = tok
        for item in raw.get("refresh_tokens", []):
            tok = RefreshToken.model_validate(item)
            self.refresh_tokens[tok.token] = tok

    def _save(self) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "clients": [c.model_dump(mode="json") for c in self.clients.values()],
            "access_tokens": [t.model_dump(mode="json") for t in self.access_tokens.values()],
            "refresh_tokens": [t.model_dump(mode="json") for t in self.refresh_tokens.values()],
        }
        tmp = STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, STATE_PATH)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.clients[client_info.client_id] = client_info
        self._save()

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        code = secrets.token_urlsafe(32)
        self.auth_codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + 600,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return self.auth_codes.get(authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self.auth_codes.pop(authorization_code.code, None)

        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)

        self.access_tokens[access_token] = AccessToken(
            token=access_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time() + ACCESS_TOKEN_TTL_SECONDS),
        )
        self.refresh_tokens[refresh_token] = RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
        )

        token = OAuthToken(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            refresh_token=refresh_token,
            scope=" ".join(authorization_code.scopes),
        )
        self._save()
        return token

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        return self.refresh_tokens.get(refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        access_token = secrets.token_urlsafe(32)
        new_refresh_token = secrets.token_urlsafe(32)
        effective_scopes = scopes or refresh_token.scopes

        self.refresh_tokens.pop(refresh_token.token, None)
        self.access_tokens[access_token] = AccessToken(
            token=access_token,
            client_id=client.client_id,
            scopes=effective_scopes,
            expires_at=int(time.time() + ACCESS_TOKEN_TTL_SECONDS),
        )
        self.refresh_tokens[new_refresh_token] = RefreshToken(
            token=new_refresh_token,
            client_id=client.client_id,
            scopes=effective_scopes,
        )

        token = OAuthToken(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            refresh_token=new_refresh_token,
            scope=" ".join(effective_scopes),
        )
        self._save()
        return token

    async def load_access_token(self, token: str) -> AccessToken | None:
        access_token = self.access_tokens.get(token)
        if access_token and access_token.expires_at and access_token.expires_at < time.time():
            self.access_tokens.pop(token, None)
            self._save()
            return None
        return access_token

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self.access_tokens.pop(token.token, None)
        self.refresh_tokens.pop(token.token, None)
        self._save()
