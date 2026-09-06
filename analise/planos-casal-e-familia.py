# -*- coding: utf-8 -*-
"""Dois planos: Casal (2 adultos) e Família (2 adultos + até 2 crianças).
A parte infantil é outra caixa, não a mesma em dobro."""
def brl(v,c=2): return ("R$ %s"%f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v,c=0): return f"{v*100:.{c}f}%"
ENT=2.50; COM=.15

ADULTO=[
 ("PÃO","2 fatias de pão de fermentação longa","120 g",1.92),
 ("PÃO","2 mini croissants","2 un",4.00),
 ("PROTEÍNA","2 ovos cozidos","2 un",1.80),
 ("PROTEÍNA","Queijo colonial","60 g",2.16),
 ("PROTEÍNA","Peito de peru","60 g",1.92),
 ("POTINHOS","Geleia em mini-pote","25 g",1.20),
 ("POTINHOS","Manteiga em tablete","2×10 g",0.92),
 ("POTINHOS","Pesto","30 g",2.05),
 ("FRUTA","Meio avocado, com casca","150 g",2.70),
 ("FRUTA","Fruta da estação","200 g",1.00),
 ("DOCE","2 mini cookies","2 un",2.40),
 ("EXTRAS","Iogurte natural com mel","100 g",1.80),
 ("EXTRAS","Granola da casa","30 g",0.60),
 ("EXTRAS","Sal e pimenta em sachê","2+2",0.10),
 ("EXTRAS","Cartão com o nome do hóspede","1",0.20),
 ("BEBIDA","Café da casa em garrafa térmica","500 ml",1.80),
]
EMB_CASAL=[("Caixa kraft + adesivo",1.50),("2 marmitinhas com tampa",0.70),
           ("Garrafa térmica em comodato",0.48),("Papéis, guardanapos, talheres",0.55),
           ("Sacola kraft",0.45)]

KIDS=[
 ("PÃO","6 pães de queijo","150 g",4.80),
 ("DOCE","2 mini bolos ou fatias","150 g",4.20),
 ("DOCE","2 mini cookies","2 un",2.40),
 ("BEBIDA","Leite com achocolatado","400 ml",2.60),
 ("FRUTA","2 bananas ou fruta cortada","—",0.50),
 ("POTINHOS","Manteiga e geleia extras","—",2.12),
 ("EXTRAS","2 iogurtes pequenos","2×80 g",2.40),
 ("EXTRAS","Cartão com o nome da criança","1",0.20),
]
EMB_KIDS=[("Caixa menor, colorida",1.20),("Garrafinha do achocolatado",0.80),
          ("Marmitinha extra",0.35),("Papéis e canudo",0.35)]

def mostra(titulo,itens,embs,extra_ins=0,extra_emb=0):
    print("\n"+"="*88); print(titulo); print("="*88)
    b=None; ins=0
    for bl,d,q,c in itens:
        if bl!=b: print(f"\n  {bl}"); b=bl
        print(f"    {d:<44}{q:>10}{brl(c):>10}"); ins+=c
    print(f"\n  {'':<46}{'insumo':>10}{brl(ins):>10}")
    emb=sum(c for _,c in embs)
    for d,c in embs: print(f"    {d:<44}{'':>10}{brl(c):>10}")
    print(f"  {'':<46}{'embalagem':>10}{brl(emb):>10}")
    custo=(ins+emb)*1.03
    print(f"  {'':<46}{'CUSTO':>10}{brl(custo):>10}")
    return ins,emb,custo

iA,eA,cA=mostra("PLANO CASAL · 2 adultos",ADULTO,EMB_CASAL)
iK,eK,cK=mostra("A PARTE INFANTIL · até 2 crianças",KIDS,EMB_KIDS)
cF=(iA+iK+eA+eK)*1.03

print("\n"+"="*88); print("POR QUE A PARTE INFANTIL NÃO É A DE ADULTO EM DOBRO"); print("="*88)
print("""  Criança de 6 anos não come pesto, avocado, peito de peru nem café.
  Come pão de queijo, bolo, achocolatado, fruta, cookie e iogurte.

  Montar a caixa família como "duas caixas de casal" custaria mais e
  entregaria metade do que a criança quer. A parte infantil sai mais barata
  POR PESSOA e agrada mais — os dois ao mesmo tempo.

    Adulto    """ + brl(cA/2) + """/pessoa
    Criança   """ + brl(cK/2) + """/pessoa

  E o cartãozinho com o nome da criança é o item de R$ 0,20 que faz o pai
  pedir de novo na manhã seguinte.""")

print("\n"+"="*88); print("OS DOIS PLANOS"); print("="*88)
print(f"  {'Plano':<34}{'Preço':>9}{'Custo':>10}{'CMV':>7}{'Comissão':>11}{'Sobra':>11}{'Margem':>9}")
for nome,custo,preco in (("Casal · 2 adultos",cA,99),
                         ("Família · 2 adultos + 2 crianças",cF,169),
                         ("Família · 2 adultos + 2 crianças",cF,179)):
    s=preco-custo-ENT-preco*COM
    print(f"  {nome:<34}{brl(preco,0):>9}{brl(custo):>10}{pc(custo/preco):>7}{brl(preco*COM):>11}{brl(s):>11}{pc(s/preco):>9}")

sC=99-cA-ENT-99*COM; sF=169-cF-ENT-169*COM
print(f"\n  A Família a R$ 169 é 1,7× o preço da Casal, mas sobra {sF/sC:.1f}× — porque a")
print(f"  entrega é a mesma e a comissão é proporcional. Mesma moto, mesmo minuto.")
print(f"  E R$ 169 lê como bom negócio contra duas caixas de casal ({brl(198,0)}).")

print("\n"+"="*88); print("E QUANDO A FAMÍLIA TEM SÓ UMA CRIANÇA?"); print("="*88)
cri=(iK/2+eK/2)*1.03
print(f"  Cobrar Família cheia de quem tem 1 criança é injusto e perde pedido.")
print(f"  Solução: Casal + criança avulsa.")
print(f"\n  {'':<30}{'Preço':>9}{'Custo':>10}{'Sobra':>11}")
print(f"  {'Casal':<30}{brl(99,0):>9}{brl(cA):>10}{brl(sC):>11}")
print(f"  {'+ 1 criança':<30}{brl(35,0):>9}{brl(cri):>10}{brl(35-cri-35*COM):>11}   sem entrega extra")
print(f"  {'+ 2 crianças (= Família)':<30}{brl(69,0):>9}{brl(cri*2):>10}{brl(69-cri*2-69*COM):>11}")
print(f"\n  Casal R$ 99 + R$ 35 por criança dá R$ 169 para duas — bate com o plano fechado.")
print(f"  Uma linha só de preço, funciona para 2, 3 ou 4 pessoas, e o hóspede paga o que usa.")
