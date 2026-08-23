@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "fix: fetch_tickers sem filtro + busca USDT*BRL em todos simbolos"
git push origin master:main --force
echo DONE
pause