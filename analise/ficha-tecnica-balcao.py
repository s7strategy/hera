# -*- coding: utf-8 -*-
"""Ficha técnica real do balcão. Preço de venda por peso decide a margem."""
def brl(v,c=2): return ("R$ %s" % f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v): return f"{v*100:.0f}%"

# custo por quilo — atacado, referência 2026
ITENS = [
 ("Açaí (balde 10 kg a R$ 175)", 17.50, "base"),
 ("Banana",                       6.00, "fruta"),
 ("Manga",                        8.00, "fruta"),
 ("Aveia em flocos",             10.00, "cereal"),
 ("Uva",                         14.00, "fruta"),
 ("Kiwi",                        16.00, "fruta"),
 ("Calda de chocolate",          18.00, "calda"),
 ("Leite condensado",            19.00, "calda"),
 ("Granola",                     20.00, "cereal"),
 ("Amendoim triturado",          25.00, "extra"),
 ("Morango",                     28.00, "fruta"),
 ("Paçoca",                      30.00, "extra"),
 ("Bala de goma",                30.00, "extra"),
 ("Confete de chocolate",        50.00, "caro"),
 ("Leite em pó / Ninho",         48.00, "caro"),
 ("Nutella",                     65.00, "caro"),
 ("Ovomaltine",                  70.00, "caro"),
 ("Castanha de caju",            75.00, "caro"),
]
PRECOS = [59.90, 69.90, 74.90]

print("="*104)
print("PARTE 1 · O QUE CADA ITEM DO BALCÃO CUSTA — E QUANTO SOBRA A CADA PREÇO DE VENDA")
print("="*104)
print(f"  {'Item':<32}{'Custo/kg':>11}" + "".join(f"{'CMV a '+brl(p,2):>16}" for p in PRECOS))
print("  "+"-"*100)
for nome,custo,_ in ITENS:
    linha=f"  {nome:<32}{brl(custo):>11}"
    for p in PRECOS:
        cmv=custo/p
        marca = " PREJUÍZO" if cmv>1 else ("  ruim" if cmv>.75 else "")
        linha+=f"{pc(cmv)+marca:>16}"
    print(linha)
print(f"""
  >>> Tudo sai da mesma balança pelo mesmo preço. Um grama de banana rende
      {pc(1-6/59.90)} de margem; um grama de castanha de caju dá PREJUÍZO de {brl(75-59.90)} por quilo.
      Vender por peso é vender margem por peso.""")

print("\n"+"="*104)
print("PARTE 2 · UMA TIGELA DE VERDADE — 415 g")
print("="*104)
def tigela(nome, comp, preco):
    custo=sum(g/1000*c for g,c in comp.values())
    peso=sum(g for g,_ in comp.values())
    venda=peso/1000*preco
    emb=1.10; quebra=custo*0.03
    total=custo+emb+quebra
    print(f"\n  {nome}  ·  venda por {brl(preco)}/kg")
    print(f"    {'Componente':<26}{'gramas':>9}{'R$/kg':>10}{'custo':>10}")
    for k,(g,c) in comp.items():
        print(f"    {k:<26}{g:>9}{brl(c):>10}{brl(g/1000*c):>10}")
    print(f"    {'':<26}{peso:>9}{'':>10}{brl(custo):>10}")
    print(f"    {'+ embalagem (copo, tampa, colher, sacola)':<45}{brl(emb):>10}")
    print(f"    {'+ quebra 3%':<45}{brl(quebra):>10}")
    print(f"    {'CUSTO TOTAL':<45}{brl(total):>10}")
    print(f"    {'PREÇO DE VENDA':<45}{brl(venda):>10}")
    print(f"    {'SOBRA BRUTA':<45}{brl(venda-total):>10}   ->  CMV de {pc(total/venda)}")
    return total/venda

pesada = {"Açaí":(255,17.50),"Frutas (banana, manga, uva)":(55,9.00),
          "Granola e aveia":(40,16.00),"Calda e leite condensado":(30,18.50),
          "Ninho, ovomaltine, confete":(35,58.00)}
leve   = {"Açaí":(270,17.50),"Frutas (banana, manga, uva)":(70,9.00),
          "Granola e aveia":(45,16.00),"Calda e leite condensado":(25,18.50),
          "Ninho, ovomaltine, confete":(5,58.00)}
r=[]
for nome,comp in (("TIGELA PESADA · cliente carrega no caro",pesada),
                  ("TIGELA LEVE · caro em porção fechada",leve)):
    for p in (59.90, 74.90):
        r.append((nome,p,tigela(nome,comp,p)))

print("\n"+"="*104)
print("PARTE 3 · O RESUMO QUE DECIDE TUDO")
print("="*104)
print(f"  {'Cenário':<44}{'a R$ 59,90/kg':>18}{'a R$ 74,90/kg':>18}")
print("  "+"-"*80)
print(f"  {'Cliente carrega no caro (35 g de premium)':<44}{pc(r[0][2]):>18}{pc(r[1][2]):>18}")
print(f"  {'Premium em porção fechada (5 g)':<44}{pc(r[2][2]):>18}{pc(r[3][2]):>18}")
print(f"""
  >>> DUAS ALAVANCAS, E AS DUAS SÃO SUAS:
      1. O PREÇO. Passar de R$ 59,90 para R$ 74,90 derruba o CMV em {abs(r[2][2]-r[3][2])*100:.0f} pontos.
         E só a marca própria pode fazer isso — a Degusta ancora em R$ 5,99/100 g.
      2. O LAYOUT DO BALCÃO. Tirar o premium do livre acesso derruba mais {abs(r[1][2]-r[3][2])*100:.0f} pontos.""")

print("\n"+"="*104)
print("PARTE 4 · A CONTA DO ANO — SEM FAMÍLIA NO BALCÃO")
print("="*104)
SM=1_621; CLT=SM*1.4
# 1 fixo nos 8 meses abertos + 4 extras em jan/fev + 2 extras em dez/mar
folha = CLT*8 + CLT*4*2 + CLT*2*2
print(f"""  Equipe (hibernando de maio a agosto):
    1 fixo, 8 meses abertos ............. {brl(CLT*8,0):>11}
    +4 extras em janeiro e fevereiro .... {brl(CLT*4*2,0):>11}   (5 pessoas no pico, troca de turno)
    +2 extras em dezembro e março ....... {brl(CLT*2*2,0):>11}   (3 pessoas)
    FOLHA ANUAL ......................... {brl(folha,0):>11}
""")
def dre(fat,cmv,folha,alug=30_000,ovh=14_400,mkt=.035,imp=.0594,cart=.046):
    return fat - fat*cmv - folha - fat*imp - fat*cart - fat*mkt - alug - ovh
CEN=[("Degusta · R$ 59,90/kg · balcão solto", 365_040, .385),
     ("Degusta · R$ 59,90/kg · balcão gerido",365_040, .355),
     ("Própria · R$ 74,90/kg · balcão solto", 389_376, .315),
     ("Própria · R$ 74,90/kg · balcão gerido",389_376, .274)]
print(f"  {'Cenário':<42}{'Faturam.':>12}{'CMV':>7}{'Lucro/ano':>13}{'Margem':>9}{'Payback':>10}")
print("  "+"-"*95)
for nome,fat,cmv in CEN:
    l=dre(fat,cmv,folha)
    print(f"  {nome:<42}{brl(fat,0):>12}{pc(cmv):>7}{brl(l,0):>13}{l/fat*100:>8.1f}%{51_800/l*12:>8.1f} m")
print(f"""
  >>> Sem família no balcão e com equipe de verdade (5 no pico), a marca própria
      com preço de R$ 74,90/kg e balcão bem montado entrega {pc(dre(389_376,.274,folha)/389_376)} de margem.
      Manter a Degusta a R$ 59,90 com balcão solto entrega {pc(dre(365_040,.385,folha)/365_040)}.
      A diferença é de {brl(dre(389_376,.274,folha)-dre(365_040,.385,folha),0)} por ano.""")
