# -*- coding: utf-8 -*-
"""Modelo v2 - variantes operacionais e grade de cenarios."""
MESES = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
DIAS  = [31,28,31,30,31,30,31,31,30,31,30,31]
CLI   = [170,120,55,30,18,14,22,14,18,26,35,90]   # clientes/dia base
ALTA  = ("Dez","Jan","Fev","Mar")
PICO  = ("Jan","Fev")

FAIXAS=[(180_000,.040,0),(360_000,.073,5_940),(720_000,.095,13_860),
        (1_800_000,.107,22_500),(3_600_000,.143,87_300),(4_800_000,.190,378_000)]
def aliq(r):
    for t,n,d in FAIXAS:
        if r<=t: return max((r*n-d)/r,0) if r else 0
    return .19
def brl(v): return ("R$ %s" % f"{v:,.0f}").replace(",",".")

class C:
    def __init__(s,nome,ticket,cmv,fluxo,capex,roy_mes,roy_pct,mkt_rede,
                 al_alta,al_baixa,f_pico,f_alta,f_baixa,mkt,ovh,fechado=(),curto=""):
        d=dict(locals()); d.pop('s'); s.__dict__.update(d)

def dre(c,mult=1.0):
    fat=0; L=[]
    cl=[x*c.fluxo*mult*d for x,d in zip(CLI,DIAS)]
    rec=[0 if m in c.fechado else x*c.ticket for m,x in zip(MESES,cl)]
    fat=sum(rec); a=aliq(fat)
    for i,m in enumerate(MESES):
        r=rec[i]; fechado = m in c.fechado
        cmv=r*c.cmv
        taxas=r*.028 + r*.12*.152
        imp=r*a
        alug=(c.al_alta if m in ALTA else c.al_baixa)          # aluguel corre mesmo fechado
        folha=0 if fechado else (c.f_pico if m in PICO else c.f_alta if m in ALTA else c.f_baixa)
        ovh=c.ovh*(0.35 if fechado else 1.0)
        roy=(0 if fechado and c.roy_mes else c.roy_mes)+r*c.roy_pct+r*c.mkt_rede
        mkt=r*c.mkt
        lucro=r-cmv-taxas-imp-alug-folha-ovh-roy-mkt
        L.append(dict(m=m,r=r,cmv=cmv,taxas=taxas,imp=imp,alug=alug,folha=folha,
                      ovh=ovh,roy=roy,mkt=mkt,lucro=lucro,cli=0 if fechado else cl[i]))
    return L,fat,a

def kpi(c,mult=1.0):
    L,fat,a=dre(c,mult); lu=sum(x["lucro"] for x in L)
    return dict(nome=c.nome,curto=c.curto,fat=fat,lucro=lu,marg=lu/fat if fat else 0,
                pb=c.capex/lu*12 if lu>0 else None,capex=c.capex,
                neg=sum(1 for x in L if x["lucro"]<0),
                burn=-sum(x["lucro"] for x in L if x["lucro"]<0),
                roy=sum(x["roy"] for x in L),L=L)

# =============================== VARIANTES ===============================
A = C("A · Franquia D'gusta — operação padrão (12 meses)",25,.385,1.00,225_000,
      2_000,0,.02, 6_000,3_800, 22_000,14_000,6_000, .015,4_200,curto="Franquia 12m")
A2= C("A2 · Franquia D'gusta — enxuta na baixa",25,.385,1.00,225_000,
      2_000,0,.02, 6_000,3_800, 22_000,13_000,4_200, .015,3_600,curto="Franquia enxuta")
B = C("B · Marca própria elevada — 12 meses",32,.325,.88,235_000,
      0,0,0, 6_000,3_800, 22_000,14_000,4_500, .035,4_200,curto="Própria 12m")
B2= C("B2 · Marca própria elevada — hiberna mai–ago",32,.325,.88,235_000,
      0,0,0, 6_000,3_800, 22_000,14_000,4_500, .035,4_200,
      fechado=("Mai","Jun","Jul","Ago"),curto="Própria hiberna")
H = C("C · Marca própria sob HERA (custos compartilhados)",32,.300,.92,185_000,
      0,0,0, 6_000,3_800, 20_000,12_500,4_000, .025,3_200,curto="HERA 12m")
H2= C("C2 · Marca própria sob HERA — hiberna mai–ago",32,.300,.92,185_000,
      0,0,0, 6_000,3_800, 20_000,12_500,4_000, .025,3_200,
      fechado=("Mai","Jun","Jul","Ago"),curto="HERA hiberna")

print("="*104)
print("PARTE 2 · VARIANTES OPERACIONAIS — CENÁRIO BASE DE FLUXO")
print("="*104)
print(f"{'Variante':<46}{'Faturam.':>12}{'Lucro ano':>12}{'Marg.':>8}{'Payback':>10}{'Meses<0':>9}{'Burn baixa':>13}")
print("-"*104)
for c in (A,A2,B,B2,H,H2):
    k=kpi(c)
    pb = f"{k['pb']:.0f} m" if k['pb'] else "nunca"
    print(f"{c.nome:<46}{brl(k['fat']):>12}{brl(k['lucro']):>12}{k['marg']*100:>7.1f}%{pb:>10}{k['neg']:>9}{brl(k['burn']):>13}")

# =============================== GRADE DE CENARIOS ===============================
print("\n"+"="*104)
print("PARTE 3 · GRADE DE CENÁRIOS — sensibilidade ao fluxo de verão")
print("="*104)
CEN=[("Pessimista (-30%)",.70),("Conservador (-15%)",.85),("Base",1.00),
     ("Otimista (+20%)",1.20),("Ponto excepcional (+40%)",1.40)]
print(f"{'Cenário':<26}"+"".join(f"{c.curto:>19}" for c in (A2,B2,H2)))
print("-"*104)
for nome,m in CEN:
    row=f"{nome:<26}"
    for c in (A2,B2,H2):
        k=kpi(c,m); lu=k['lucro']
        row+=f"{brl(lu):>19}"
    print(row)
print(f"\n{'(payback em meses)':<26}"+"".join(
    f"{(f'{kpi(c)[chr(112)+chr(98)]:.0f}m' if kpi(c)['pb'] else 'nunca'):>19}" for c in (A2,B2,H2)))

# =============================== BREAK-EVEN ===============================
print("\n"+"="*104)
print("PARTE 4 · PONTO DE EQUILÍBRIO — de quanto fluxo cada modelo precisa para empatar no ano")
print("="*104)
for c in (A,A2,B,B2,H,H2):
    lo,hi=.05,4.0
    for _ in range(80):
        mid=(lo+hi)/2
        if kpi(c,mid)['lucro']<0: lo=mid
        else: hi=mid
    k=kpi(c,hi)
    jan=k['L'][0]
    print(f"{c.nome:<46} precisa de {hi*100:>5.0f}% do fluxo base  "
          f"(≈{jan['cli']/31:>4.0f} clientes/dia em jan · faturamento anual {brl(k['fat'])})")

# =============================== 5 ANOS ===============================
print("\n"+"="*104)
print("PARTE 5 · CAIXA ACUMULADO EM 5 ANOS (contrato de franquia = 5 anos)")
print("="*104)
print("Premissa: ano 1 a 70% do fluxo base (curva de maturação), ano 2 a 90%, anos 3-5 a 100%.")
CURVA=[.70,.90,1.0,1.0,1.0]
print(f"{'Variante':<46}{'Ano1':>12}{'Ano2':>12}{'Ano3-5/ano':>13}{'Acum. 5 anos':>15}{'- CAPEX':>14}")
print("-"*104)
res={}
for c in (A2,B2,H2):
    anos=[kpi(c,m)['lucro'] for m in CURVA]
    acum=sum(anos); res[c.curto]=acum-c.capex
    print(f"{c.nome:<46}{brl(anos[0]):>12}{brl(anos[1]):>12}{brl(anos[2]):>13}{brl(acum):>15}{brl(acum-c.capex):>14}")

print("\n"+"-"*104)
print("CUSTO TOTAL DA FRANQUIA EM 5 ANOS (o que você paga à franqueadora):")
tf=40_000
roy5=sum(kpi(A2,m)['roy'] for m in CURVA)
fat5=sum(kpi(A2,m)['fat'] for m in CURVA)
markup=fat5*(.385-.325)   # sobrepreço estimado de insumos vs compra direta
print(f"  Taxa de franquia inicial ....................... {brl(tf):>12}")
print(f"  Royalties fixos + fundo de propaganda (5 anos) . {brl(roy5):>12}")
print(f"  Sobrepreço de insumos vs compra direta (6 p.p.)  {brl(markup):>12}")
print(f"  {'TOTAL EXTRAÍDO EM 5 ANOS':<46} {brl(tf+roy5+markup):>12}   "
      f"= {(tf+roy5+markup)/fat5*100:.1f}% do faturamento do período")

# ============================================================================
# PARTES 6 A 10 — teste adversarial, temporada, aluguel
# ============================================================================
def mk(nome,ticket,cmv,fluxo,capex,roy_mes,mkt_rede,f_baixa=4_200,mkt=.015,ovh=3_600,curto=""):
    return C(nome,ticket,cmv,fluxo,capex,roy_mes,0,mkt_rede,6_000,3_800,
             22_000,13_000,f_baixa,mkt,ovh,curto=curto)

BASE_PROPRIA = mk("propria",32,.325,.88,235_000,0,0,4_200,.035,3_600)
def lucro(c,m=1.0): return kpi(c,m)['lucro']
LP = lucro(BASE_PROPRIA)

print("\n"+"="*104)
print("PARTE 6 · TESTE ADVERSARIAL — sob quais premissas a FRANQUIA passa à frente?")
print("="*104)
print(f"Referência: marca própria elevada entrega {brl(LP)}/ano no cenário base.\n")

print("6.1 · Sensibilidade ao SOBREPREÇO de insumos da franqueadora")
for cmv in (.30,.32,.34,.36,.385,.41):
    l=lucro(mk("f",25,cmv,1.00,225_000,2_000,.02))
    print(f"     CMV {cmv*100:>5.1f}% -> {brl(l):>12} ({brl(l-LP)} vs própria)  "
          f"{'FRANQUIA VENCE' if l>LP else 'própria vence'}")

print("\n6.2 · Sensibilidade ao ROYALTY mensal fixo")
for roy in (0,1_160,1_500,2_000,3_000):
    l=lucro(mk("f",25,.385,1.00,225_000,roy,.02))
    print(f"     Royalty {brl(roy):>10} -> {brl(l):>12}  {'FRANQUIA VENCE' if l>LP else 'própria vence'}")

print("\n6.3 · Pull de marca: quanto fluxo extra a franquia precisaria trazer")
for extra in (0,.10,.20,.30,.40,.50):
    l=lucro(mk("f",25,.385,1.00+extra,225_000,2_000,.02))
    print(f"     +{extra*100:>3.0f}% de fluxo -> {brl(l):>12}  {'FRANQUIA VENCE' if l>LP else 'própria vence'}")

print("\n6.4 · MESMO TICKET dos dois lados (custo puro de ser franqueado)")
for t in (25,28,32,36):
    lf=lucro(mk("f",t,.385,1.00,225_000,2_000,.02))
    lp=lucro(mk("p",t,.325,1.00,235_000,0,0,4_200,.035,3_600))
    print(f"     Ticket R$ {t}: franquia {brl(lf):>12} | própria {brl(lp):>12} | custo {brl(lp-lf)}")

print("\n"+"="*104)
print("PARTE 8 · MODELO 'SÓ TEMPORADA' (nov–mar)")
print("="*104)
FORA=("Abr","Mai","Jun","Jul","Ago","Set","Out")
def temporada(nome,ticket,cmv,fluxo,capex,roy_mes,mkt_rede,al_mes,mkt,ovh,curto):
    return C(nome,ticket,cmv,fluxo,capex,roy_mes,0,mkt_rede,al_mes,0,22_000,13_000,0,mkt,ovh,
             fechado=FORA,curto=curto)
TF=temporada("Franquia D'gusta · só temporada",25,.385,1.00,225_000,2_000,.02,9_500,.015,3_600,"")
TP=temporada("Marca própria elevada · só temporada",32,.325,.88,180_000,0,0,9_500,.035,3_600,"")
TH=temporada("Marca própria HERA · só temporada",32,.300,.92,140_000,0,0,9_500,.025,2_800,"")
for c in (A2,TF,B2,TP,H2,TH):
    k=kpi(c); pb=f"{k['pb']:.0f} m" if k['pb'] else "nunca"
    print(f"  {c.nome:<48}{brl(c.capex):>11}{brl(k['lucro']):>12}{k['marg']*100:>8.1f}%{pb:>10}"
          f"{k['lucro']/c.capex*100:>8.0f}% a.a.")

print("\n"+"="*104)
print("PARTE 10 · SENSIBILIDADE AO ALUGUEL")
print("="*104)
print(f"{'Aluguel alta/baixa':<28}{'Franquia':>16}{'Própria':>16}{'HERA':>16}")
for alta,baixa in ((4_000,2_500),(6_000,3_800),(8_000,5_000),(10_000,6_000),(14_000,8_000)):
    row=f"R$ {alta:,}/{baixa:,}".replace(",",".").ljust(28)
    for b in (A2,B2,H2):
        c=C(b.nome,b.ticket,b.cmv,b.fluxo,b.capex,b.roy_mes,0,b.mkt_rede,alta,baixa,
            b.f_pico,b.f_alta,b.f_baixa,b.mkt,b.ovh,fechado=b.fechado)
        row+=f"{brl(kpi(c)['lucro']):>16}"
    print(row)
