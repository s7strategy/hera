# -*- coding: utf-8 -*-
"""Quanto o preço do quilo da polpa vale no lucro do ano. Marca própria, espaço kids."""
def brl(v,c=0): return ("R$ %s" % f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")

FAT=639_000; TICKET=32
LUCRO=252_097          # curva-conservadora.py, marca própria + espaço kids
CMV=.274               # insumo total sobre a receita
G_ACAI=.270            # quilos de polpa na tigela de 415 g
P_BASE=17.50           # R$/kg — balde de 10 kg a R$ 175

TIGELAS=FAT/TICKET
KG=TIGELAS*G_ACAI
INSUMO=FAT*CMV
ACAI=KG*P_BASE
RESTO=INSUMO-ACAI

print("="*80); print("A BASE"); print("="*80)
print(f"  Tigelas no ano                        {TIGELAS:>12,.0f}".replace(",","."))
print(f"  Polpa consumida                       {KG:>12,.0f} kg".replace(",","."))
print(f"  Baldes de 10 kg                       {KG/10:>12,.0f}".replace(",","."))
print(f"  Insumo total ({CMV*100:.1f}% da receita)      {brl(INSUMO):>12}")
print(f"    · polpa a {brl(P_BASE,2)}/kg              {brl(ACAI):>12}")
print(f"    · complementos e embalagem          {brl(RESTO):>12}")
print(f"\n  Cada R$ 1,00 no quilo vale {brl(KG)} por ano.")
print(f"  Cada R$ 10 no balde de 10 kg vale {brl(KG)} por ano.")

print("\n"+"="*80); print("LUCRO DO ANO CONFORME O PREÇO DA POLPA"); print("="*80)
print(f"  {'Balde 10 kg':>12}{'R$/kg':>9}{'Insumo':>12}{'CMV':>8}{'Lucro do ano':>15}{'Payback':>10}")
INV=62_550
for balde in (145,155,165,175,185,195,210,230,260,350):
    p=balde/10
    ins=RESTO+KG*p
    luc=LUCRO-(p-P_BASE)*KG
    print(f"  {brl(balde):>12}{p:>9.2f}{brl(ins):>12}{ins/FAT*100:>7.1f}%{brl(luc):>15}{INV/luc*12:>8.1f} m")

print(f"\n  Mesmo com a polpa ao dobro ({brl(P_BASE*2,2)}/kg), sobram {brl(LUCRO-P_BASE*KG)} no ano.")

print("\n"+"="*80); print("O QUE PEDIR EM CADA ORÇAMENTO"); print("="*80)
for i,q in enumerate([
    "Preço do quilo por tipo de polpa — tradicional, zero, com guaraná",
    "Preço do balde de 10 kg fechado, na tabela e à vista",
    "Frete até Garopaba: incluso, à parte, ou grátis acima de quanto",
    "Pedido mínimo por entrega",
    "Prazo de entrega e frequência garantida em janeiro",
    "Embalagem: vende junto? Copo, tampa, colher e sacola, a que preço",
    "Complementos: granola, leite em pó, calda, fruta — vende? a quanto",
    "Reajuste na entressafra (set–dez) e se dá para travar preço em agosto",
    "Prazo de pagamento e desconto à vista",
    "Amostra grátis para teste cego antes de fechar",
]): print(f"  {i+1:>2}. {q}")
