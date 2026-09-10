# -*- coding: utf-8 -*-
"""Quantos sabores cabem, e quantos DEVEM ficar abertos.
A pergunta que parece de equipamento é, na verdade, de giro."""

FAT   = [170,130,55,25,16,15,17,15,17,24,45,110]   # R$ mil, curva do modelo
MES   = "jan fev mar abr mai jun jul ago set out nov dez".split()
DIAS  = [31,28,31,30,31,30,31,31,30,31,30,31]
BALDES_ANO = 539                                    # do curva-conservadora.py

# mix realista: os 5 de açaí carregam a venda, a cauda é fina
MIX = [
 ("Açaí guaraná tradicional", .30), ("Açaí natural", .12), ("Açaí zero", .05),
 ("Açaí com banana", .07),          ("Açaí com morango", .06),
 ("Creme americano", .08),          ("Creme de cupuaçu", .05), ("Café com cacau", .03),
 ("Frozen grego natural", .04),     ("Frozen grego morango", .04),
 ("Paçoca", .03), ("Graviola", .025), ("Pitaya", .025),
 ("Tapioca com coco", .02), ("Cookies and cream", .03), ("Ferrero", .03),
]
assert abs(sum(p for _,p in MIX)-1) < 1e-9

tot = sum(FAT)
bal_mes = [BALDES_ANO*f/tot for f in FAT]

print("="*78)
print("BALDES POR MÊS  ·  539 no ano, distribuídos pela curva de faturamento")
print("="*78)
print(f"{'':5}"+"".join(f"{m:>6}" for m in MES))
print(f"{'bal':5}"+"".join(f"{b:>6.0f}" for b in bal_mes))
print(f"{'/dia':5}"+"".join(f"{b/d:>6.1f}" for b,d in zip(bal_mes,DIAS)))

print()
print("="*78)
print("DIAS PARA ACABAR UM BALDE ABERTO  ·  com os 16 sabores expostos")
print("="*78)
print(f"{'sabor':26}{'jan':>7}{'fev':>7}{'abr':>7}{'jun':>7}{'set':>7}{'dez':>7}")
alvo = [0,1,3,5,8,11]
LIM = 21          # acima disso, cristaliza e queima no freezer aberto
criticos = []
for nome, p in MIX:
    linha = ""
    for i in alvo:
        d = 1/(bal_mes[i]*p/DIAS[i])          # dias para girar 1 balde
        linha += f"{d:>7.0f}" if d < 999 else "    ---"
    print(f"{nome:26}{linha}")
    if 1/(bal_mes[5]*p/DIAS[5]) > LIM: criticos.append(nome)

print()
print("-"*78)
print(f"Em junho, {len(criticos)} dos 16 passam de {LIM} dias para girar um balde:")
for c in criticos: print("   ·", c)

print()
print("="*78)
print("QUANTOS SABORES ABERTOS, POR MÊS")
print("="*78)
print(f"{'mês':6}{'baldes/dia':>12}{'16 abertos':>13}{'8 abertos':>12}{'recomendado':>14}")
for i,m in enumerate(MES):
    bd = bal_mes[i]/DIAS[i]
    # giro médio do sabor MEDIANO em cada cenário
    g16 = 1/(bd*MIX[7][1])                      # café com cacau, 3% — o meio da cauda
    g8  = 1/(bd*(MIX[7][1]/ .60))               # com 8 sabores, a cauda some e o mix concentra
    if   bd >= 3.0: rec = "16 · todos"
    elif bd >= 1.5: rec = "12"
    elif bd >= 0.7: rec = "8"
    else:           rec = "6 · núcleo"
    print(f"{m:6}{bd:>12.1f}{g16:>11.0f} d{g8:>10.0f} d{rec:>14}")

print()
print("="*78)
print("QUANTOS BALDES CABEM  ·  a conta para fazer com a trena na sexta")
print("="*78)
BALDE = 28   # Ø ~26-27 cm + 1 cm de folga
print(f"Balde de 10 L redondo ocupa ~{BALDE} x {BALDE} cm de chão, ~31 cm de altura.\n")
print(f"{'interno (C x L)':<18}{'colunas':>9}{'fileiras':>10}{'baldes':>9}   sabores vivos")
for c,l in [(90,50),(110,55),(115,56),(120,60),(130,60),(150,65),(170,70),(190,75)]:
    col, fil = c//BALDE, l//BALDE
    n = col*fil
    print(f"{c} x {l} cm{'':<6}{col:>9}{fil:>10}{n:>9}   {n}")

print("""
O DEGRAU ESTÁ NA LARGURA, NÃO NO COMPRIMENTO.
Abaixo de 56 cm de largura interna só cabe UMA fileira, e o freezer inteiro
serve 3 ou 4 sabores por mais comprido que seja. De 56 cm em diante, dobra.

A altura NÃO multiplica: balde empilhado não se serve, vira estoque.
Quem decide o número de sabores é a ÁREA DO FUNDO, não a litragem.""")

print()
print("="*78)
print("A TEMPERATURA É OUTRA ARMADILHA")
print("="*78)
print("""Freezer comum de casa trabalha a -18 ou -22 °C. Gelato e açaí se servem
entre -12 e -14 °C. A -18 o produto vira pedra: a concha entorta, o
atendente demora o dobro e a fila para.

Na sexta: ver se o termostato REGULA e até que faixa. Se for fixo em -18,
o freezer serve de estoque, e o de serviço tem que ser outro.""")
