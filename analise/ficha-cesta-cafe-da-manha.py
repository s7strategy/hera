# -*- coding: utf-8 -*-
"""Ficha técnica da cesta de café da manhã, item a item. Preços de atacado
praticados em SC. Nada quente além do café na garrafa térmica."""
def brl(v,c=2): return ("R$ %s"%f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v,c=0): return f"{v*100:.{c}f}%"

# preço de atacado por quilo, litro ou unidade
P={
 "pao":24.00,        # pão de fermentação natural, atacado de padaria      R$/kg
 "croissant":3.80,   # congelado pré-assado premium                        R$/un
 "manteiga":46.00,   # R$/kg
 "geleia":36.00,     # artesanal                                           R$/kg
 "queijo":44.00,     # colonial ou minas, produção de SC                   R$/kg
 "peru":38.00,       # peito de peru ou presunto                           R$/kg
 "fruta":8.00,       # da estação: banana, mamão, melão                    R$/kg
 "bolo":32.00,       # bolo caseiro, atacado                               R$/kg
 "cafe":55.00,       # em grão                                             R$/kg
 "laranja":4.50,     # rende ~50% em suco                                  R$/kg
 "leite":5.00,       # R$/L
}
EMB={
 "caixa":4.00,       # papelão personalizado, tiragem pequena
 "caixa_vol":2.20,   # a partir de 1.000 unidades
 "copo_termico":1.60,# 500 ml com tampa, por unidade
 "potinho":0.70,     # 60 g de geleia
 "miudos":1.50,      # papel manteiga, guardanapo, talher, etiqueta
 "sacola":0.80,
}

def linha(desc,chave,qtd,unid="g"):
    if unid=="g":   c=P[chave]*qtd/1000
    elif unid=="ml":c=P[chave]*qtd/1000
    else:           c=P[chave]*qtd
    return (desc,f"{qtd:g} {unid}",c)

ESSENCIAL=[
 linha("Pão de fermentação natural","pao",200),
 linha("Manteiga","manteiga",40),
 linha("Geleia artesanal","geleia",60),
 linha("Fruta da estação","fruta",250),
 linha("Café da casa, garrafa térmica 500 ml","cafe",36),
]
EMB_ESS=[("Caixa de papelão","1",EMB["caixa"]),
         ("Copo térmico 500 ml + tampa","1",EMB["copo_termico"]),
         ("Potinho de geleia","1",EMB["potinho"]),
         ("Miúdos e sacola","—",EMB["miudos"]+EMB["sacola"])]

COMPLETO=ESSENCIAL+[
 linha("Croissant pré-assado","croissant",2,"un"),
 linha("Queijo colonial","queijo",80),
 linha("Peito de peru","peru",80),
 linha("Bolo da vitrine","bolo",100),
 linha("Suco de laranja 300 ml","laranja",600),
]
EMB_COMP=EMB_ESS+[("Segundo potinho e papéis","—",1.20)]

def mostra(nome,itens,embs,preco,comissao=.15,entrega=2.50):
    print("\n"+"="*80); print(f"{nome.upper()} · 2 pessoas"); print("="*80)
    print(f"  {'Item':<40}{'Quantidade':>14}{'Custo':>12}")
    sub=0
    for d,q,c in itens:
        print(f"  {d:<40}{q:>14}{brl(c):>12}"); sub+=c
    print(f"  {'':<40}{'subtotal insumo':>14}{brl(sub):>12}")
    print()
    sube=0
    for d,q,c in embs:
        print(f"  {d:<40}{q:>14}{brl(c):>12}"); sube+=c
    print(f"  {'':<40}{'subtotal embalagem':>14}{brl(sube):>12}")
    custo=(sub+sube)*1.03      # 3% de quebra e sobra
    print(f"\n  {'CUSTO DA CAIXA':<40}{'com 3% de quebra':>14}{brl(custo):>12}")
    com=preco*comissao
    sobra=preco-custo-entrega-com
    print(f"\n  Preço de venda                                            {brl(preco):>12}")
    print(f"  − custo da caixa                                          {brl(-custo):>12}   {pc(custo/preco)}")
    print(f"  − entrega                                                 {brl(-entrega):>12}")
    print(f"  − comissão do proprietário (15%)                          {brl(-com):>12}")
    print(f"  = SOBRA                                                   {brl(sobra):>12}   {pc(sobra/preco)}")
    print(f"\n  Uma tigela de açaí sobra R$ 22,95. Esta caixa sobra {sobra/22.95:.1f}×.")
    return custo,sobra

c1,s1=mostra("Essencial",ESSENCIAL,EMB_ESS,69)
c2,s2=mostra("Completo",COMPLETO,EMB_COMP,99)

print("\n"+"="*80); print("O QUE A CONTA MOSTRA"); print("="*80)
print(f"  Eu tinha estimado R$ 31,90 de insumo para a caixa de casal, por arredondamento.")
print(f"  Montada de verdade, a Completo custa {brl(c2)} — {pc(c2/31.90-1)} a mais.")
print(f"  A Essencial custa {brl(c1)}, e é ela que encosta no âncora de R$ 30/pessoa.")
print(f"\n  A R$ 60 (o âncora), a Completo daria prejuízo de {brl(60-c2-2.50-9.00)}.")
print(f"  A R$ 60, a Essencial ainda sobraria {brl(60-c1-2.50-9.00)} — apertado, mas de pé.")
print("\n  Conclusão: R$ 30/pessoa não paga uma cesta com queijo, frios, bolo e suco.")
print("  Quem cobra isso está vendendo pão, manteiga, café e fruta — a Essencial.")

print("\n"+"="*80); print("AS TRÊS ALAVANCAS DE CUSTO"); print("="*80)
print(f"  {'Alavanca':<44}{'Economia':>12}{'Custo depois':>15}")
alav=[("Caixa em tiragem de 1.000+ (R$ 4,00 → R$ 2,20)",EMB["caixa"]-EMB["caixa_vol"]),
      ("Garrafa térmica de comodato em vez de copo",EMB["copo_termico"]*0.7),
      ("Suco de fruta da estação em vez de laranja",1.20),
      ("Queijo e frios do mesmo fornecedor, fatiados",1.40)]
acum=c2
for n,e in alav:
    acum-=e*1.03
    print(f"  {n:<44}{brl(-e):>12}{brl(acum):>15}")
print(f"\n  Com as quatro, a Completo cai de {brl(c2)} para {brl(acum)} — {pc(acum/99)} de CMV a R$ 99.")
