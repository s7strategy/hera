# -*- coding: utf-8 -*-
"""Plano do açaí com espaço kids — Praia da Ferrugem. Curva conservadora acordada."""
def brl(v,c=0): return ("R$ %s" % f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v): return f"{v*100:.1f}%"
MES=["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
DIAS=[31,28,31,30,31,30,31,31,30,31,30,31]
C=[170,130,55,25,16,15,17,15,17,24,45,110]        # milhares de R$
FAT=sum(C)*1000
TICKET=32; TETO_DIA=350
FAIXAS=[(180_000,.040,0),(360_000,.073,5_940),(720_000,.095,13_860),(1_800_000,.107,22_500)]
def aliq(r):
    for t,n,d in FAIXAS:
        if r<=t: return max((r*n-d)/r,0)
    return .143
SM=1_621; CLT=SM*1.4
FOLHA=CLT*(5*2+4*1+3*2+1*7)          # 5 no pico, 4 em dez, 3 em mar/nov, 1 o resto
ALUG=30_000                           # R$ 2.500/mês com luz e água inclusas
OVH=14_400                            # gás, contador, PDV, internet, limpeza
KIDS_OP=7_539; KIDS_CAPEX=25_550
INV=29_800+12_380+KIDS_CAPEX+22_000   # gasto + marca + kids + giro
CMV_GERIDO=.274; CMV_SOLTO=.315

print("="*88); print("A CURVA"); print("="*88)
print(f"  {'Mês':<6}{'Faturamento':>14}{'Clientes/dia':>14}{'% do ano':>11}")
for i,m in enumerate(MES):
    print(f"  {m:<6}{brl(C[i]*1000):>14}{C[i]*1000/TICKET/DIAS[i]:>12.0f}/d{C[i]/sum(C)*100:>10.1f}%")
print(f"  {'ANO':<6}{brl(FAT):>14}")
print(f"\n  Dez+jan+fev = {brl((C[0]+C[1]+C[11])*1000)} ({(C[0]+C[1]+C[11])/sum(C)*100:.0f}% do ano)")
print(f"  Pico de janeiro: {C[0]*1000/TICKET/31:.0f} cli/dia = {C[0]*1000/TICKET/31/TETO_DIA*100:.0f}% do teto do ponto")

print("\n"+"="*88); print("DRE ANUAL"); print("="*88)
for cmv,rot in ((CMV_GERIDO,"balcão gerido"),(CMV_SOLTO,"balcão solto")):
    a=aliq(FAT)
    L=[("Faturamento",FAT),(f"Insumo (CMV {pc(cmv)})",-FAT*cmv),("Folha",-FOLHA),
       (f"Impostos · Simples {pc(a)}",-FAT*a),("Cartão e delivery 4,6%",-FAT*.046),
       ("Marketing 3,5%",-FAT*.035),("Aluguel",-ALUG),("Overhead",-OVH),
       ("Espaço kids · seguro e monitor",-KIDS_OP)]
    lucro=sum(v for _,v in L)
    print(f"\n  ── {rot.upper()} ──")
    for n,v in L:
        print(f"    {n:<34}{brl(v):>13}{('  '+pc(abs(v)/FAT)) if n!='Faturamento' else '':>9}")
    print(f"    {'LUCRO DO ANO':<34}{brl(lucro):>13}   {pc(lucro/FAT)}")
    print(f"    {'Payback sobre '+brl(INV):<34}{'':>13}   {INV/lucro*12:.1f} meses")

print("\n"+"="*88); print("SENSIBILIDADE"); print("="*88)
for m,rot in ((.75,"−25%"),(.85,"−15%"),(1.0,"conforme o plano"),(1.15,"+15%")):
    f=FAT*m; a=aliq(f)
    l=f-f*CMV_GERIDO-FOLHA-f*a-f*.046-f*.035-ALUG-OVH-KIDS_OP
    print(f"  Verão {rot:<18}{brl(f):>13}   lucro {brl(l):>12}   margem {pc(l/f):>7}   payback {INV/l*12:>4.1f} m")

print("\n"+"="*88); print("INVESTIMENTO"); print("="*88)
ITENS=[("Obra e adequação dos 35 m²",9_000),("Mobiliário do deck",6_000),
       ("Estoque inicial",9_000),("Marketing de abertura",2_500),
       ("Licenças, alvará e balança INMETRO",1_800),("Abrir a tela do deck",1_500),
       ("Marca própria (embalagem, adesivagem, INPI, uniforme)",12_380),
       ("Espaço kids",KIDS_CAPEX),("Capital de giro (volta)",22_000)]
for n,v in ITENS: print(f"  {n:<52}{brl(v):>11}")
print(f"  {'TOTAL':<52}{brl(sum(v for _,v in ITENS)):>11}")
print("\n  Equipamento pesado (balcão, freezers, vitrine, PDV) já comprado — fora desta conta.")
