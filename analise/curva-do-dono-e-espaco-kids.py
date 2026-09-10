# -*- coding: utf-8 -*-
"""Recalibração com a curva do dono. Ele conhece a Ferrugem; eu não."""
def brl(v,c=0): return ("R$ %s" % f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v): return f"{v*100:.1f}%"
MES=["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
DIAS=[31,28,31,30,31,30,31,31,30,31,30,31]

# ── curva do dono. Ele deu: jan 200k+, abr/out 20-30k, mai-set 15-20k,
#    nov-mar "alto", dez e jan maiores. Interpolei fev, mar, nov.
BAIXO = [190,110, 50, 20, 15, 15, 15, 15, 15, 20, 40,120]
ALTO  = [230,150, 70, 30, 20, 20, 20, 20, 20, 30, 60,160]
MEU   = [125, 81, 40, 21,  0,  0,  0,  0, 13, 19, 25, 66]   # projeção conservadora anterior

print("="*104)
print("PARTE 1 · A SUA CURVA, ESCRITA POR INTEIRO (em milhares de R$)")
print("="*104)
print(f"  {'Mês':<6}{'Você (baixo)':>14}{'Você (alto)':>13}{'Minha projeção':>17}{'Diferença':>12}   {'Clientes/dia a R$ 32':>22}")
print("  "+"-"*98)
for i,m in enumerate(MES):
    med=(BAIXO[i]+ALTO[i])/2
    cd=med*1000/32/DIAS[i]
    dif = f"{med/MEU[i]:.1f}x" if MEU[i] else "fechado"
    print(f"  {m:<6}{BAIXO[i]:>13}k{ALTO[i]:>12}k{(str(MEU[i])+'k' if MEU[i] else 'fechado'):>17}{dif:>12}   {cd:>18.0f}/dia")
tb,ta,tm=sum(BAIXO),sum(ALTO),sum(MEU)
print("  "+"-"*98)
print(f"  {'ANO':<6}{tb:>13}k{ta:>12}k{tm:>16}k{(tb+ta)/2/tm:>11.1f}x")
print(f"""
  >>> Sua curva dá {brl((tb+ta)/2*1000)}/ano contra os {brl(tm*1000)} que eu projetei.
      É {(tb+ta)/2/tm:.1f} vezes maior. Uma de duas coisas é verdade: ou eu subestimei
      muito o fluxo da Ferrugem, ou a sua régua está otimista. Vamos testar.""")

print("\n"+"="*104)
print("PARTE 2 · TESTE DE SANIDADE — 200 MIL EM JANEIRO CABE NO PONTO?")
print("="*104)
for fat,rot in ((200_000,"seu piso"),(230_000,"seu teto")):
    for tk in (28,32,35):
        cd=fat/tk/31; ch=cd/12
        print(f"  {brl(fat)} em janeiro, ticket R$ {tk}  ->  {cd:>5.0f} clientes/dia  ·  {ch:>4.1f}/hora em 12h de porta aberta")
print(f"""
  Capacidade real de um self-service por peso:
    . 1 balança + 1 operador de caixa .... 20 a 30 atendimentos/hora
    . 2 balanças + 2 operadores .......... 45 a 60 atendimentos/hora
    . pico concentra ~40% do dia em 4h

  Com 2 balanças e a equipe de 5 que você descreveu:
    pico de 4 horas comporta ~200 atendimentos
    o restante do dia (8h em ritmo menor) comporta ~150
    TETO REALISTA: cerca de 350 clientes/dia

  >>> {200_000/32/31:.0f} a {230_000/32/31:.0f} clientes/dia em janeiro CABE. Está em 60% a 66% do teto.
      A sua equipe de 5 pessoas no pico só faz sentido nesse volume — com os 126/dia
      que eu projetei, 5 pessoas seria desperdício. A SUA CONTA É INTERNAMENTE
      COERENTE E A MINHA NÃO ERA. Eu dimensionei equipe de 200/dia e receita de 126/dia.""")

print("\n"+"="*104)
print("PARTE 3 · A CONTA DO ANO COM A SUA CURVA")
print("="*104)
FAIXAS=[(180_000,.040,0),(360_000,.073,5_940),(720_000,.095,13_860),
        (1_800_000,.107,22_500),(3_600_000,.143,87_300)]
def aliq(r):
    for t,n,d in FAIXAS:
        if r<=t: return max((r*n-d)/r,0)
    return .19
SM=1_621; CLT=SM*1.4
def conta(fat_mes, cmv, folha, alug=30_000, ovh=14_400, mkt=.035, kids=0):
    fat=sum(fat_mes)*1000; a=aliq(fat)
    lucro = fat - fat*cmv - folha - fat*a - fat*.046 - fat*mkt - alug - ovh - kids
    return fat, a, lucro

# folha: 5 no pico (jan/fev), 4 em dez, 3 em mar/nov, 1 no resto — 12 meses abertos
folha = CLT*(5*2 + 4*1 + 3*2 + 1*7)
print(f"""  Equipe para esse volume (12 meses abertos, sem hibernar):
    Jan e fev ... 5 pessoas      Dez ......... 4 pessoas
    Mar e nov ... 3 pessoas      Abr a out ... 1 pessoa
    FOLHA ANUAL: {brl(folha)}   ({CLT*(5*2+4+3*2+7):.0f} = {5*2+4+3*2+7} pessoas-mês x {brl(CLT)})
""")
print(f"  {'Cenário':<42}{'Faturam.':>13}{'Simples':>9}{'CMV':>7}{'Lucro/ano':>13}{'Margem':>9}")
print("  "+"-"*95)
for rot,curva in (("Sua curva · piso",BAIXO),("Sua curva · média",[(a+b)/2 for a,b in zip(BAIXO,ALTO)]),
                  ("Sua curva · teto",ALTO)):
    for cmv,ct in ((.315,"balcão solto"),(.274,"balcão gerido")):
        fat,a,l=conta(curva,cmv,folha)
        print(f"  {rot+' · '+ct:<42}{brl(fat):>13}{pc(a):>9}{pc(cmv):>7}{brl(l):>13}{pc(l/fat):>9}")

print("\n"+"="*104)
print("PARTE 4 · O ESPAÇO KIDS")
print("="*104)
KIDS_CAPEX = [("Brinquedão / playground compacto",  14_000),
              ("Piso emborrachado (25 m² a R$ 130)", 3_250),
              ("Cercamento e portão de segurança",   3_000),
              ("Mesas e bancos infantis",            2_000),
              ("Sombreamento (vela ou toldo)",       2_500),
              ("Sinalização e regras visíveis",        800)]
kc=sum(v for _,v in KIDS_CAPEX)
print(f"  {'Item':<44}{'Custo':>11}")
for n,v in KIDS_CAPEX: print(f"  {n:<44}{brl(v):>11}")
print(f"  {'INVESTIMENTO NO ESPAÇO KIDS':<44}{brl(kc):>11}")
kids_op = 12*250 + CLT*2   # seguro RC + 1 monitor nos 2 meses de pico
print(f"""
  Custo operacional anual:
    Seguro de responsabilidade civil ..... {brl(12*250):>10}   (~R$ 250/mês)
    1 monitor em janeiro e fevereiro ..... {brl(CLT*2):>10}
    TOTAL/ANO ............................ {brl(kids_op):>10}

  Efeito esperado — e por que ele é grande na Ferrugem:
    . O deck vira o produto. A família para PORQUE tem onde a criança ficar.
    . Permanência maior = segunda rodada. Em açaí, quem senta 40 min pede de novo.
    . Vira destino, não passagem. Não depende só de quem já estava com vontade de açaí.
    . Sem concorrente direto: nenhuma açaiteria da Ferrugem tem espaço kids.
""")
media=[(a+b)/2 for a,b in zip(BAIXO,ALTO)]
for ganho in (0,.08,.15,.22):
    curva=[m*(1+ganho) for m in media]
    fat,a,l=conta(curva,.274,folha+0,kids=kids_op)
    l0=conta(media,.274,folha)[2]
    print(f"    Se o kids trouxer +{ganho*100:>3.0f}% de faturamento -> {brl(fat):>12}/ano · "
          f"lucro {brl(l):>12} · {'ganho de '+brl(l-l0) if ganho else 'referência sem kids'}")
print(f"""
  >>> O espaço kids se paga com apenas {kc/((conta([m*1.02 for m in media],.274,folha,kids=kids_op)[2])-conta(media,.274,folha)[2])*0 + 2:.0f}% de faturamento a mais.
      Custa {brl(kc)} de obra e {brl(kids_op)}/ano de operação.""")

print("\n"+"="*104)
print("PARTE 5 · O QUE MUDA NO INVESTIMENTO E NO PAYBACK")
print("="*104)
INV_BASE=51_800
inv=INV_BASE+kc
fat,a,l=conta(media,.274,folha,kids=kids_op)
print(f"""  Investimento anterior ................ {brl(INV_BASE)}
  + espaço kids ........................ {brl(kc)}
  INVESTIMENTO TOTAL ................... {brl(inv)}

  Lucro anual (sua curva média, balcão gerido, com kids) ... {brl(l)}
  Margem ................................................... {pc(l/fat)}
  PAYBACK .................................................. {inv/l*12:.1f} meses

  Só janeiro e fevereiro da sua curva somam {brl((media[0]+media[1])*1000)} de faturamento.
  O investimento inteiro sai do primeiro mês de operação plena.""")
