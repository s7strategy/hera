# -*- coding: utf-8 -*-
"""Ficha da cesta de café da manhã, item a item, em duas colunas:
o que eu tinha cotado de primeira, e o que sai comprando em volume."""
def brl(v,c=2): return ("R$ %s"%f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v,c=0): return f"{v*100:.{c}f}%"

def bloco(titulo,linhas):
    print("\n"+"="*94); print(titulo); print("="*94)
    print(f"  {'Item':<38}{'Qtd':>10}{'1ª cotação':>13}{'Em volume':>13}{'Economia':>12}")
    a=b=0
    for d,q,x,y in linhas:
        print(f"  {d:<38}{q:>10}{brl(x):>13}{brl(y):>13}{brl(y-x):>12}")
        a+=x; b+=y
    print(f"  {'':<38}{'SUBTOTAL':>10}{brl(a):>13}{brl(b):>13}{brl(b-a):>12}")
    return a,b

# ── embalagem ────────────────────────────────────────────────────────────────
EMB=[
 ("Caixa de papelão + adesivo da marca","1",4.00,1.50),
 ("Marmitinha com tampa 250 ml","2",0.00,0.70),
 ("Copo de papel 300 ml com tampa","2",1.60,0.60),
 ("Potinho de geleia 60 g","1",0.70,0.35),
 ("Papel manteiga, guardanapo, talher","—",1.50,0.55),
 ("Sacola kraft","1",0.80,0.45),
]
ea,eb=bloco("EMBALAGEM — onde eu estava mais errado",EMB)
print(f"\n  A 1ª coluna usava caixa PERSONALIZADA em tiragem pequena (R$ 4,00) e garrafa")
print(f"  térmica de 500 ml (R$ 1,60). Em volume, caixa kraft com adesivo sai R$ 1,50 e")
print(f"  copo de papel com tampa sai R$ 0,30 a unidade. Você estava certo: {brl(eb)}, não {brl(ea)}.")
print(f"\n  ⚠ O copo de papel entrega o café MORNO às 9h. Alternativa melhor e mais barata:")
print(f"    garrafa térmica de comodato — R$ 22 a unidade, ~50 usos, 10% de perda =")
print(f"    {brl(22/50*1.10)} por entrega. Mais barata que dois copos E o café chega quente.")

# ── insumo ───────────────────────────────────────────────────────────────────
ESS=[
 ("Pão de fermentação natural","200 g",4.80,3.20),
 ("Manteiga em tablete","20 g",1.84,0.92),
 ("Geleia artesanal","60 g",2.16,1.68),
 ("Fruta da estação","250 g",2.00,1.25),
 ("Café em grão","36 g",1.98,1.80),
]
ia,ib=bloco("INSUMO DA ESSENCIAL",ESS)
print(f"\n  Pão: R$ 24/kg era preço de balcão. Atacado de padaria em volume fica em R$ 16/kg.")
print(f"  Manteiga: 40 g para 200 g de pão era exagero — 20 g em tablete basta e é R$ 46/kg mesmo.")
print(f"  Fruta: comprando na feira ou no CEASA, R$ 5/kg em vez de R$ 8.")

EXTRA=[
 ("Croissant mini pré-assado","2 un",7.60,4.00),
 ("Queijo colonial","60 g",3.52,2.16),
 ("Peito de peru","60 g",3.04,1.92),
 ("Bolo da vitrine","100 g",3.20,2.80),
 ("Suco de laranja 250 ml","500 g",2.70,1.75),
]
xa,xb=bloco("O QUE A COMPLETO ACRESCENTA",EXTRA)
print(f"\n  Croissant: R$ 3,80 era de croissant grande. Mini sai R$ 2,00 — e a caixa já leva 200 g de pão.")
print(f"  Queijo colonial: R$ 44/kg era preço de varejo. Atacado em SC fica em R$ 36/kg,")
print(f"  e 60 g para duas pessoas já é fatia generosa. Você tinha razão nos dois pontos.")

# ── fechamento ───────────────────────────────────────────────────────────────
print("\n"+"="*94); print("AS DUAS CAIXAS, COM PREÇO DE VOLUME"); print("="*94)
ENTREGA=2.50; COM=.15
CAIXAS=[("Essencial",ib+eb,59),("Essencial",ib+eb,69),
        ("Completo",ib+xb+eb+0.35,89),("Completo",ib+xb+eb+0.35,99)]
print(f"  {'Kit':<14}{'Preço':>8}{'Custo':>10}{'CMV':>7}{'Entrega':>9}{'Comissão':>10}{'Sobra':>10}{'vs açaí':>10}")
for n,c,p in CAIXAS:
    c*=1.03; s=p-c-ENTREGA-p*COM
    print(f"  {n:<14}{brl(p,0):>8}{brl(c):>10}{pc(c/p):>7}{brl(ENTREGA):>9}{brl(p*COM):>10}{brl(s):>10}{s/22.95:>9.1f}×")
print(f"\n  Antes, com a cotação de primeira: Essencial custava {brl((ia+ea)*1.03)} e Completo {brl((ia+xa+ea)*1.03)}.")
print(f"  Agora: {brl((ib+eb)*1.03)} e {brl((ib+xb+eb+0.35)*1.03)}. A Completo caiu {pc(1-((ib+xb+eb+0.35)*1.03)/((ia+xa+ea)*1.03))}.")

print("\n"+"="*94); print("SOBRE FAZER O PRÓPRIO PÃO"); print("="*94)
print("  A 30 caixas/dia no verão são 6 kg de pão por dia. Isso não é padaria, são 12 pães.")
print("  Mas fazer exige o que o formato terceirizado justamente evitou:")
print("    · forno                  R$ 14.000 de capex que a loja não ia gastar")
print("    · câmara de fermentação  R$  9.000 — fermentação natural precisa de controle")
print("    · alguém às 5h da manhã  todo dia, o ano inteiro")
print("    · área licenciada        RDC 216/2004 — não pode ser em casa")
print(f"\n  A economia é de {brl(4.80-3.20)}/caixa comprando a R$ 16/kg em vez de R$ 24.")
print(f"  Sobre 1.485 caixas/ano são {brl((4.80-3.20)*1485)}. O forno sozinho leva 9 anos para pagar.")
print("  Negociar a padaria para R$ 16/kg resolve o mesmo problema por zero de investimento.")
