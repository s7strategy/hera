# -*- coding: utf-8 -*-
"""A Essencial repensada: mais substanciosa, sem quebrar a regra de que
nada quente viaja bem."""
def brl(v,c=2): return ("R$ %s"%f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v,c=0): return f"{v*100:.{c}f}%"
EMB=3.68; ENT=2.50; COM=.15

def caixa(nome,itens,preco,nota=""):
    ins=sum(c for _,_,c in itens)
    custo=(ins+EMB)*1.03
    s=preco-custo-ENT-preco*COM
    print("\n"+"="*84); print(nome); print("="*84)
    for d,q,c in itens: print(f"  {d:<44}{q:>10}{brl(c):>10}")
    print(f"  {'':<44}{'insumo':>10}{brl(ins):>10}")
    print(f"  {'':<44}{'embalagem':>10}{brl(EMB):>10}")
    print(f"  {'':<44}{'CUSTO':>10}{brl(custo):>10}")
    print(f"\n  A {brl(preco,0)}   CMV {pc(custo/preco)}   sobra {brl(s)}   margem {pc(s/preco)}   {s/22.95:.1f}× uma tigela")
    if nota: print(f"\n  {nota}")
    return custo,s

caixa("ESSENCIAL v1 — a que você achou básica demais",[
 ("Pão de fermentação natural","200 g",3.20),("Manteiga em tablete","20 g",0.92),
 ("Geleia em mini-pote","25 g",1.20),("Fruta da estação","250 g",1.25),
 ("Café na garrafa térmica","500 ml",1.80)],69)

caixa("ESSENCIAL v2 — do jeito que você pediu, com misto quente",[
 ("2 mistos quentes prensados","2 un",6.40),
 ("2 ovos cozidos","2 un",1.80),
 ("Fatia de bolo","100 g",2.80),
 ("Fruta da estação","200 g",1.00),
 ("Café na garrafa térmica","500 ml",1.80)],69,
 "⚠ O misto é o problema. Ver abaixo.")

c3,s3=caixa("ESSENCIAL v3 — o mesmo prato, montado pelo hóspede",[
 ("2 fatias de pão de fermentação longa","120 g",1.92),
 ("Queijo colonial","60 g",2.16),
 ("Peito de peru","60 g",1.92),
 ("2 ovos cozidos","2 un",1.80),
 ("Manteiga em tablete","20 g",0.92),
 ("Geleia em mini-pote","25 g",1.20),
 ("Fatia de bolo","100 g",2.80),
 ("Fruta da estação","200 g",1.00),
 ("Café na garrafa térmica","500 ml",1.80)],79,
 "Mesmo conteúdo do misto — pão, queijo e peru — só que o hóspede monta.\n  Pode comer frio, pode prensar. Chega perfeito nos dois casos.")

print("\n"+"="*84); print("POR QUE O MISTO QUENTE É O ITEM MAIS ARRISCADO DA CAIXA"); print("="*84)
print("""  Prensado às 6h30, embalado, entregue às 8h. O que acontece nesse tempo:

    · o vapor preso na embalagem encharca o pão por dentro
    · o queijo derretido esfria e endurece, vira borracha
    · a manteiga da chapa solidifica e deixa o pão gorduroso
    · em papel alumínio ou plástico é pior — o vapor não sai

  Você tem uma regra boa na caixa inteira: nada quente viaja. Ovo cozido,
  bolo, fruta, pão, queijo, frios, iogurte — tudo isso chega igual ao que
  saiu. O misto é a única exceção, e é justo o item que o hóspede vai
  julgar primeiro.

  Uma caixa ruim na primeira manhã não perde um pedido. Perde o
  proprietário que indicou — e com ele todas as estadias daquele imóvel.

  SE MESMO ASSIM QUISER O MISTO, dá para reduzir o risco:
    · embalar em papel manteiga e saco kraft, nunca plástico ou alumínio
    · prensar por último, com a moto já na porta
    · só para entregas de até 15 minutos de rota
    · nunca no pico, quando a rota tem 10 paradas""")

print("\n"+"="*84); print("AS TRÊS LADO A LADO"); print("="*84)
print(f"  {'':<38}{'Preço':>8}{'Custo':>10}{'Sobra':>10}{'Viaja bem?':>14}")
for n,p,c,s,v in [("v1 · a básica",69,12.41,43.74,"sim"),
                  ("v2 · com misto quente",69,18.00,38.15,"NÃO"),
                  ("v3 · o hóspede monta",79,19.78,44.87,"sim")]:
    print(f"  {n:<38}{brl(p,0):>8}{brl(c):>10}{brl(s):>10}{v:>14}")
print(f"\n  A v3 custa {brl(19.78-18.00)} a mais que a v2, sobra {brl(44.87-38.15)} a mais e não tem risco.")
print(f"  E ainda dá ao hóspede a escolha: comer frio ou prensar na hora.")
print(f"\n  Com a v3 a R$ 79, a linha fica:")
print(f"    Essencial  R$  79   sobra {brl(44.87)}")
print(f"    Completa   R$  99   sobra {brl(50.49)}")
print(f"    Família    R$ 179   sobra ~{brl(95)}")
print(f"  Diferença de só {brl(50.49-44.87)} entre Essencial e Completa — perto demais.")
print(f"  Ou a Essencial desce para R$ 69 (sobra {brl(69-19.78-2.50-69*.15)}), ou a Completa sobe para R$ 109.")
