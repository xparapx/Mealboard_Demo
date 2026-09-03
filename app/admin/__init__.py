"""관리 앱(tailnet 전용, ADMIN_PORT 8101). 공개 앱과 별도 프로세스 — Funnel 은 8100 만 내보내고, 이 앱은 `tailscale serve --https=8443` 으로만.
3a: 순수 로직(auth.identify · guard.needs_force)과 테스트. 3b 에서 create_app(라우터·미들웨어·워치독)이 붙는다."""
