"""Tests Runner — container separado pra orquestrar bateria E2E (Sprint L).

Roda em imagem dedicada (Dockerfile.tests) com pytest + deepeval + Java +
allure CLI. Não fica na imagem principal da API pra manter ela leve.

Endpoints internos (sem auth — restrito à rede Docker):
    POST   /run                      → dispara run
    GET    /runs                     → histórico
    GET    /runs/{id}                → detalhe
    GET    /runs/{id}/events         → SSE stream
    POST   /runs/{id}/kill           → SIGTERM
    GET    /runs/{id}/report         → allure index.html
    GET    /runs/{id}/report/{path}  → assets
"""
