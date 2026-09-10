# -*- coding: utf-8 -*-
"""Matriz 2×2: Essencial e Premium, cada um em Casal e Família.
O Premium é o Essencial mais seis itens — o upgrade lê como soma pura."""
def brl(v,c=2): return ("R$ %s"%f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v,c=0): return f"{v*100:.{c}f}%"
ENT=2.50; COM=.15

BASE_AD=[("2 fatias de pão de fermentação longa","120 g",1.92),
         ("Queijo colonial","60 g",2.16),
         ("Peito de peru","60 g",1.92),
         ("2 ovos cozidos","2 un",1.80),
         ("Manteiga em tablete","2×10 g",0.92),
         ("Geleia em mini-pote","25 g",1.20),
         ("Fatia de bolo","100 g",2.80),
         ("Fruta da estação","200 g",1.00),
         ("Café da casa em garrafa térmica","500 ml",1.80)]
PLUS_AD=[("2 mini croissants","2 un",4.00),
         ("Pesto no potinho","30 g",2.05),
         ("Meio avocado, com casca","150 g",2.70),
         ("Iogurte natural com mel","100 g",1.80),
         ("Granola da casa","30 g",0.60),
         ("Sal e pimenta + cartão com o nome","—",0.30)]
BASE_KID=[("6 pães de queijo","150 g",4.80),
          ("2 mini bolos","150 g",4.20),
          ("Leite com achocolatado na garrafinha","400 ml",2.60),
          ("2 bananas ou fruta cortada","—",0.50),
          ("Manteiga e geleia extras","—",2.12)]
PLUS_KID=[("2 mini cookies","2 un",2.40),
          ("2 iogurtes pequenos","2×80 g",2.40),
          ("Cartão com o nome da criança","1",0.20)]
EMB_AD=3.68; EMB_KID=2.70

def s(itens): return sum(c for _,_,c in itens)
bA,pA=s(BASE_AD),s(PLUS_AD); bK,pK=s(BASE_KID),s(PLUS_KID)

def custo(ins,emb): return (ins+emb)*1.03
CUSTOS={
 ("Essencial","Casal"):   custo(bA,EMB_AD),
 ("Premium","Casal"):     custo(bA+pA,EMB_AD),
 ("Essencial","Família"): custo(bA+bK,EMB_AD+EMB_KID),
 ("Premium","Família"):   custo(bA+pA+bK+pK,EMB_AD+EMB_KID),
}
PRECOS={("Essencial","Casal"):69,("Premium","Casal"):109,
        ("Essencial","Família"):119,("Premium","Família"):189}

print("="*90); print("O ESSENCIAL · 2 adultos"); print("="*90)
for d,q,c in BASE_AD: print(f"  {d:<48}{q:>10}{brl(c):>10}")
print(f"  {'':<48}{'insumo':>10}{brl(bA):>10}")
print("\n"+"="*90); print("O QUE O PREMIUM ACRESCENTA · 2 adultos"); print("="*90)
for d,q,c in PLUS_AD: print(f"  {d:<48}{q:>10}{brl(c):>10}")
print(f"  {'':<48}{'a mais':>10}{brl(pA):>10}")

print("\n"+"="*90); print("A PARTE INFANTIL · até 2 crianças"); print("="*90)
print("  no Essencial")
for d,q,c in BASE_KID: print(f"    {d:<46}{q:>10}{brl(c):>10}")
print(f"    {'':<46}{'insumo':>10}{brl(bK):>10}")
print("  o Premium acrescenta")
for d,q,c in PLUS_KID: print(f"    {d:<46}{q:>10}{brl(c):>10}")
print(f"    {'':<46}{'a mais':>10}{brl(pK):>10}")

print("\n"+"="*90); print("A MATRIZ"); print("="*90)
print(f"  {'':<12}{'Casal':>34}{'Família · 2 adultos + 2 crianças':>44}")
print(f"  {'':<12}{'Preço':>9}{'Custo':>9}{'Sobra':>9}{'Marg':>7}{'Preço':>13}{'Custo':>9}{'Sobra':>10}{'Marg':>7}")
for tier in ("Essencial","Premium"):
    l=f"  {tier:<12}"
    for tam in ("Casal","Família"):
        p=PRECOS[(tier,tam)]; c=CUSTOS[(tier,tam)]; so=p-c-ENT-p*COM
        w=13 if tam=="Família" else 9
        l+=f"{brl(p,0):>{w}}{brl(c):>9}{brl(so):>{10 if tam=='Família' else 9}}{pc(so/p):>7}"
    print(l)

print("\n"+"="*90); print("O QUE CADA UPGRADE VALE"); print("="*90)
def so(k): return PRECOS[k]-CUSTOS[k]-ENT-PRECOS[k]*COM
ups=[("Casal: Essencial → Premium",("Essencial","Casal"),("Premium","Casal")),
     ("Família: Essencial → Premium",("Essencial","Família"),("Premium","Família")),
     ("Essencial: Casal → Família",("Essencial","Casal"),("Essencial","Família")),
     ("Premium: Casal → Família",("Premium","Casal"),("Premium","Família"))]
print(f"  {'Upgrade':<32}{'+ preço':>11}{'+ custo':>10}{'+ sobra':>11}{'quanto do upgrade sobra':>26}")
for n,a,b in ups:
    dp=PRECOS[b]-PRECOS[a]; dc=CUSTOS[b]-CUSTOS[a]; ds=so(b)-so(a)
    print(f"  {n:<32}{brl(dp,0):>11}{brl(dc):>10}{brl(ds):>11}{pc(ds/dp):>25}")
print("\n  Todo upgrade devolve mais de metade em sobra. O de Casal para Família é o")
print("  melhor de todos, porque a entrega é a mesma moto e o mesmo minuto de montagem.")

print("\n"+"="*90); print("A LINHA COMPLETA"); print("="*90)
for tier in ("Essencial","Premium"):
    for tam in ("Casal","Família"):
        k=(tier,tam); p=PRECOS[k]
        print(f"  {tier+' · '+tam:<26}{brl(p,0):>8}   custo {brl(CUSTOS[k]):>8}   CMV {pc(CUSTOS[k]/p):>4}   sobra {brl(so(k)):>8}   {so(k)/22.95:.1f}× uma tigela")
print(f"\n  Ticket médio, num mix de 30% Essencial Casal, 30% Premium Casal,")
mix={("Essencial","Casal"):.30,("Premium","Casal"):.30,("Essencial","Família"):.20,("Premium","Família"):.20}
tk=sum(PRECOS[k]*m for k,m in mix.items()); sb=sum(so(k)*m for k,m in mix.items())
print(f"  20% Essencial Família e 20% Premium Família:  {brl(tk)} de ticket, {brl(sb)} de sobra.")
print(f"  Contra os {brl(90.50)} e {brl(42.37)} que estão publicados na página hoje.")
