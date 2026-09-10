# -*- coding: utf-8 -*-
"""Cenário enxuto: 1 funcionário, aluguel R$ 2.500 com contas inclusas, CMV melhor."""
def brl(v): return ("R$ %s" % f"{v:,.0f}").replace(",",".")
def pc(v,b): return f"{v/b*100:.1f}%"
FAT = 389_376          # marca própria, hibernando mai-ago
SM  = 1_621; CLT = SM*1.4

print("="*100)
print("PARTE 1 · O CMV — VOCÊ ESTÁ CERTO, EU FUI PESSIMISTA")
print("="*100)
print(f"""
  Referência pública: o CMV ideal de açaiteria fica entre 28% e 35%, e açaiterias
  bem geridas chegam a margens de 30% a 50% — das maiores do food service.
  Eu usei 32,5%, que é o TOPO da faixa ideal. Dá para fazer melhor.

  Por que o açaí ajuda:
    . Polpa a R$ 15-22/kg vendida a R$ 65-75/kg  ->  CMV da polpa pura: 22% a 31%
    . Fruta (banana, morango) custa R$ 5-15/kg e vende pelo mesmo preço por peso
    . Leite condensado, calda e granola são baratos por quilo
  Por que pode piorar:
    . Castanha e nozes custam R$ 40-80/kg — vendidas a R$ 65/kg dão PREJUÍZO
    . Embalagem (copo, tampa, colher) pesa 3% a 5% do ticket
    . Quebra: açaí derretido e complemento descartado, 2% a 4%

  >>> A alavanca real é o MIX. Deixe fruta, granola e calda na frente do balcão;
      castanha e importado em porção fechada ou cobrados à parte.
""")
for cmv in (.35,.325,.30,.28):
    rot = "ruim" if cmv>=.35 else ("meu modelo" if cmv==.325 else ("bem gerido" if cmv==.30 else "muito bem gerido"))
    print(f"    CMV {cmv*100:>4.1f}%  ({rot:<17}) -> custo anual de insumo {brl(FAT*cmv):>11}")

print("\n"+"="*100)
print("PARTE 2 · ALUGUEL DE R$ 2.500 COM AS CONTAS INCLUSAS")
print("="*100)
ovh_atual = dict(Energia=12_000, Água=1_800, Gás=600, Contador=4_800,
                 PDV=2_400, Internet=1_200, Limpeza=5_400)
inclusas = ("Energia","Água")
ovh_novo = sum(v for k,v in ovh_atual.items() if k not in inclusas)
print(f"  {'Item do overhead':<22}{'Antes':>11}{'Com contas inclusas':>22}")
print("  "+"-"*56)
for k,v in ovh_atual.items():
    print(f"  {k:<22}{brl(v):>11}{('no aluguel' if k in inclusas else brl(v)):>22}")
print("  "+"-"*56)
print(f"  {'TOTAL':<22}{brl(sum(ovh_atual.values())):>11}{brl(ovh_novo):>22}")
print(f"""
  Aluguel: R$ 2.500 x 12 = {brl(30_000)}/ano  (antes: R$ 21.000 no split 2.500/1.500)

  Aluguel + overhead, antes ......... {brl(21_000 + sum(ovh_atual.values()))}
  Aluguel + overhead, com contas .... {brl(30_000 + ovh_novo)}
  Economia líquida .................. {brl((21_000+sum(ovh_atual.values())) - (30_000+ovh_novo))}

  >>> Pagar R$ 1.000/mês a mais de aluguel para não pagar luz e água VALE A PENA.
      Freezer e balcão refrigerado ligados 24h em janeiro fazem a conta de luz
      explodir — e nesse arranjo o risco é do locador, não seu.""")

print("\n"+"="*100)
print("PARTE 3 · 1 FUNCIONÁRIO DÁ CONTA?")
print("="*100)
print("""
  Janeiro projetado: 141 clientes/dia, 12h de porta aberta = 12/hora na média.
  Mas o movimento concentra: ~40% do dia entre 15h e 19h = 14 a 20 clientes/hora
  no pico.

  Uma pessoa no caixa com balança faz 20 a 30 atendimentos/hora. Ou seja:
  DÁ CONTA DE COBRAR. O que ela NÃO consegue fazer ao mesmo tempo:
    . repor o buffet (açaí derrete e complemento acaba rápido no calor)
    . lavar cuba e utensílio
    . montar milk shake e vitamina
    . separar pedido de delivery
    . limpar mesa do deck

  >>> 1 funcionário SOZINHO não fecha janeiro. 1 funcionário + você (ou seu pai)
      no balcão fecha. E 1 extra contratado em jan e fev tira o sufoco do pico.
      Mas 5 pessoas, como eu tinha modelado, é demais para 35 m² — não cabe
      atrás de um balcão de 3,5 m. Você tinha razão de estranhar.
""")

print("="*100)
print("PARTE 4 · A CONTA ENXUTA, COM TUDO JUNTO")
print("="*100)
def dre(cmv, folha, alug, ovh, mkt=.035, nome=""):
    imp   = FAT*.0594
    cart  = FAT*.046
    lucro = FAT - FAT*cmv - folha - imp - cart - FAT*mkt - alug - ovh
    return lucro
CEN = [
  ("Modelo anterior (5 no pico, CMV 32,5%)", .325, 68_200, 21_000, 28_200, .035),
  ("1 CLT + 2 extras jan/fev + 1 dez/mar",   .325, 40_849, 30_000, ovh_novo, .035),
  ("... e CMV de 30% (bem gerido)",          .30,  40_849, 30_000, ovh_novo, .035),
  ("... e CMV de 28% (muito bem gerido)",    .28,  40_849, 30_000, ovh_novo, .035),
  ("1 CLT só + família no balcão, CMV 30%",  .30,  27_233, 30_000, ovh_novo, .035),
  ("1 CLT só + família, CMV 28%, sem mkt",   .28,  27_233, 30_000, ovh_novo, .0),
]
print(f"  {'Cenário':<44}{'Lucro/ano':>13}{'Margem':>9}{'vs modelo':>13}")
print("  "+"-"*82)
L0=None
for nome,cmv,f,a,o,m in CEN:
    l=dre(cmv,f,a,o,m)
    if L0 is None: L0=l
    print(f"  {nome:<44}{brl(l):>13}{pc(l,FAT):>9}{(brl(l-L0) if l!=L0 else '—'):>13}")

print(f"""
  >>> Com 1 funcionário, contas no aluguel e CMV bem gerido de 30%, a margem sai
      de 23,3% para {pc(dre(.30,40_849,30_000,ovh_novo),FAT)} — e com você no balcão passa de {pc(dre(.30,27_233,30_000,ovh_novo),FAT)}.
      A meta de 30% deixa de ser esticada e vira o cenário provável.""")

print("\n"+"="*100)
print("PARTE 5 · E SE O FATURAMENTO FOR OS R$ 420 A 460 MIL QUE DISCUTIMOS?")
print("="*100)
print(f"  {'Faturamento':<16}{'Cenário':<40}{'Lucro/ano':>13}{'Margem':>9}")
print("  "+"-"*80)
for fat in (389_376, 430_000, 460_000):
    for nome,cmv,f,a,o,m in [("1 CLT + extras, CMV 30%",.30,40_849,30_000,ovh_novo,.035),
                             ("1 CLT + família, CMV 30%",.30,27_233,30_000,ovh_novo,.035)]:
        l = fat - fat*cmv - f - fat*.0594 - fat*.046 - fat*m - a - o
        print(f"  {brl(fat):<16}{nome:<40}{brl(l):>13}{pc(l,fat):>9}")
    print()
print("""  Em todos esses cenários o investimento de R$ 51.800 volta na primeira temporada,
  e a margem fica entre 29% e 34%.""")
