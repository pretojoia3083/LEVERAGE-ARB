# LEVERAGE ARB — Guia de Deploy na Nuvem (Render)

Tempo total: ~15 minutos. Você só vai clicar e colar.

## O que você precisa
- Conta GitHub (gratuita) — github.com
- Conta Render (gratuita) — render.com
- App **GitHub Desktop** instalado — desktop.github.com

---

## PASSO 1 — Subir o código para o GitHub

1. Abra o **GitHub Desktop** e faça login com sua conta GitHub.
2. Menu `File` → `Add local repository...`
3. Selecione a pasta:
   ```
   C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB
   ```
4. Se ele perguntar sobre criar um repositório, confirme (o .gitignore já está pronto).
5. Em `Summary` escreva qualquer coisa (ex: `primeiro deploy`) e clique em **Commit to main**.
6. Clique no botão **Publish repository** (topo).
   - Nome sugerido: `leverage-arb`
   - DEIXE DESMARCADO "Keep this code private" se quiser simplificar (código não tem segredos).
7. Clique em **Publish**.

## PASSO 2 — Criar o serviço na Render

1. Acesse https://dashboard.render.com e faça login.
2. Clique em **New +** → **Web Service**.
3. Clique em **Connect** ao lado do repositório `leverage-arb`.
4. Preencha:
   - **Name**: `leverage-arb`
   - **Region**: escolha `Ohio (US East)` ou `Virginia` (mais perto do Brasil)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1`
   - **Instance Type**: `Free`
5. Clique em **Create Web Service**.
6. Aguarde o build (~3-5 min). Quando ficar verde **Live**, seu link é:
   ```
   https://leverage-arb.onrender.com
   ```
   (o nome exato aparece na página do serviço)

## PASSO 3 — Manter ele acordado 24h (importante!)

O plano grátis da Render "dorme" após 15 min sem visitas.
Solução gratuita:

1. Crie conta em https://uptimerobot.com (grátis).
2. `Add New Monitor` → tipo **HTTP(s)**.
3. URL: `https://SEU-LINK.onrender.com/api/dashboard`
4. Intervalo: **5 minutos** → Save.

Pronto: o sistema roda 24h coletando simulações mesmo com seu PC desligado!

## PASSO 4 — Atualizar o código no futuro

Depois de qualquer alteração nos arquivos:
1. GitHub Desktop → commit → **Push origin**
2. A Render detecta e reinicia sozinha com o código novo.

---

## ⚠️ Limitações do plano grátis (honestidade)

| Item | Free | Pago ($7/mo) |
|------|------|--------------|
| Dorme sem ping | Sim (resolvido com UptimeRobot) | Nunca dorme |
| Banco de dados | Zera a cada redeploy* | Persistente |
| Velocidade | Compartilhada | Dedicada |

*Dica: antes de qualquer redeploy, baixe backup em `https://SEU-LINK/api/simulations?limit=9999`

## 🔐 Chaves de API?
NENHUMA chave é necessária. O sistema usa só preços públicos das corretoras.
