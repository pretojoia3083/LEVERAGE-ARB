#!/bin/bash
# LEVERAGE ARB - Oracle Cloud Setup
# Execute este script no terminal do Oracle Cloud

echo "=== LEVERAGE ARB - Instalando no Oracle Cloud ==="

# 1. Atualizar sistema
sudo apt update && sudo apt upgrade -y

# 2. Instalar Python e dependencias
sudo apt install -y python3 python3-pip python3-venv git

# 3. Clonar o repositorio
cd /home/ubuntu
git clone https://github.com/pretojoia3083/LEVERAGE-ARB.git
cd LEVERAGE ARB

# 4. Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate

# 5. Instalar dependencias
pip install -r requirements.txt

# 6. Criar arquivo .env com as chaves
cat > .env << 'EOF'
BITGET_API_KEY=bg_f6e6e91c270bae5dada159f64fc2eb18
BITGET_SECRET_KEY=95da49454e3beb531955df67477d184d4c8b2f313a54966e9c6ce55ec3bd103a
BITGET_PASSPHRASE=none
BINANCE_API_KEY=HIWvdNXyUmkDjGIqVujwkGEklkfztETmXLWIiJpOCjV80GjITFo9fvy8MEnFu5vB
BINANCE_SECRET_KEY=L3BGUtqUUFACQ7R3eFv1e8YO6FmAHBD5makaNt3MUnq1vnvtdQolf7v4YAcyPeFJ
EOF

# 7. Criar servico systemd para rodar 24/7
sudo tee /etc/systemd/system/leverage-arb.service > /dev/null << 'EOF'
[Unit]
Description=LEVERAGE ARB Scanner
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/LEVERAGE ARB
ExecStart=/home/ubuntu/LEVERAGE ARB/venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 8. Ativar e iniciar o servico
sudo systemctl daemon-reload
sudo systemctl enable leverage-arb
sudo systemctl start leverage-arb

# 9. Abrir porta no firewall
sudo ufw allow 8000/tcp

echo ""
echo "=== INSTALACAO CONCLUIDA ==="
echo "Acesse: http://SEU_IP_PUBLICO:8000"
echo ""
echo "Para ver status: sudo systemctl status leverage-arb"
echo "Para ver logs: sudo journalctl -u leverage-arb -f"
echo "Para reiniciar: sudo systemctl restart leverage-arb"
