# -*- coding: utf-8 -*-
"""Café da manhã entregue ao hóspede de Airbnb — Praia da Ferrugem.
O canal escala com proprietários parceiros, não com o parque total."""
def brl(v,c=0): return ("R$ %s"%f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v,c=1): return f"{v*100:.{c}f}%"
MES=["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
DIAS=[31,28,31,30,31,30,31,31,30,31,30,31]

# ── ocupação do Airbnb na Ferrugem ───────────────────────────────────────────
# O Airbnb reporta 53% dos alojamentos disponíveis no ano (≈47% ocupados), com
# pico de disponibilidade em jul (72%), jun (70,5%) e ago (68,4%). A curva
# abaixo reproduz esse formato, por baixo.
OCUP=[.92,.78,.45,.28,.20,.18,.22,.18,.22,.30,.42,.68]
NOITES=[5,5,4,3,3,3,3,3,3,3,4,4]
PARQUE=435          # anúncios listados na Praia da Ferrugem

CONV=.15; REPETE=.30
PED=CONV*(1+REPETE)

KITS=[("Solo",39,12.60,.25),("Casal",89,31.90,.55),("Família (4)",159,56.80,.20)]
ENTREGA=2.50        # provisão; abaixo de ~15 caixas/manhã a equipe absorve
COMISSAO=.15
TICKET=sum(p*m for _,p,_,m in KITS); CUSTO=sum(c*m for _,_,c,m in KITS)
COM=TICKET*COMISSAO; SOBRA=TICKET-CUSTO-ENTREGA-COM

print("="*88); print("A CAIXA — nada quente além do café na garrafa térmica"); print("="*88)
print(f"  {'Kit':<14}{'Venda':>9}{'Insumo':>10}{'Entrega':>9}{'Comissão':>10}{'Sobra':>10}{'CMV':>8}{'Mix':>6}")
for n,p,c,m in KITS:
    print(f"  {n:<14}{brl(p):>9}{brl(c,2):>10}{brl(ENTREGA,2):>9}{brl(p*COMISSAO,2):>10}"
          f"{brl(p-c-ENTREGA-p*COMISSAO,2):>10}{pc(c/p,0):>8}{pc(m,0):>6}")
print(f"  {'PONDERADA':<14}{brl(TICKET,2):>9}{brl(CUSTO,2):>10}{brl(ENTREGA,2):>9}{brl(COM,2):>10}"
      f"{brl(SOBRA,2):>10}{pc(CUSTO/TICKET,0):>8}")
print(f"\n  Tigela de açaí de 415 g: vende {brl(31.08,2)}, sobra {brl(22.95,2)}.")
print(f"  Caixa entregue: vende {brl(TICKET,2)}, sobra {brl(SOBRA,2)} — {SOBRA/22.95:.1f}× a tigela,")
print(f"  às 8h da manhã, com o balcão parado e sem disputar a fila de janeiro.")

def canal(u):
    return [u*DIAS[i]*OCUP[i]/NOITES[i]*PED for i in range(12)]

print("\n"+"="*88); print("VOLUME POR NÚMERO DE PARCEIROS"); print("="*88)
print(f"  {'Parceiros':<11}{'% do parque':>12}"+"".join(f"{m:>6}" for m in MES)+f"{'ANO':>8}{'pico/manhã':>12}")
for u in (50,100,200,300):
    p=canal(u)
    print(f"  {u:<11}{u/PARQUE*100:>11.0f}%"+"".join(f"{x:>6.0f}" for x in p)
          +f"{sum(p):>8.0f}{max(p)/31:>11.0f}")
print("\n  Teto operacional da manhã: ~30 caixas com 2 pessoas entre 6h30 e 9h30.")
print("  Em nenhum cenário acima a operação é a restrição — a restrição é assinar proprietário.")

# ── efeito no ano ────────────────────────────────────────────────────────────
C=[170,130,55,25,16,15,17,15,17,24,45,110]; BASE=sum(C)*1000
FAIXAS=[(180_000,.040,0),(360_000,.073,5_940),(720_000,.095,13_860),(1_800_000,.107,22_500)]
def aliq(r):
    for t,n,d in FAIXAS:
        if r<=t: return max((r*n-d)/r,0)
    return .143
SM=1_621; CLT=SM*1.4
FOLHA=CLT*(5*2+4*1+3*2+1*7); ALUG=30_000; OVH=14_400; KIDS=7_539; CMV=.274
def lucro(xf,xs):
    f=BASE+xf; a=aliq(f)
    return f,(BASE-BASE*CMV)+xs-FOLHA-f*a-f*.046-f*.035-ALUG-OVH-KIDS
f0,l0=lucro(0,0)

print("\n"+"="*88); print("O QUE FAZ NO ANO"); print("="*88)
print(f"  {'Cenário':<26}{'Faturamento':>13}{'Lucro':>13}{'Margem':>9}{'Ganho':>13}")
print(f"  {'Só a loja':<26}{brl(f0):>13}{brl(l0):>13}{pc(l0/f0):>9}{'—':>13}")
for u in (50,100,200,300):
    p=canal(u); f,l=lucro(sum(p)*TICKET,sum(p)*SOBRA)
    print(f"  {'Loja + '+str(u)+' parceiros':<26}{brl(f):>13}{brl(l):>13}{pc(l/f):>9}{'+'+brl(l-l0):>13}")

print("\n"+"="*88); print("O PRÊMIO DE VERDADE: A BAIXA TEMPORADA"); print("="*88)
p=canal(200)
print(f"  {'Mês':<6}{'Loja':>12}{'Café manhã':>12}{'Total':>12}{'% a mais':>10}{'Sobra do mês':>15}")
fix_mes=[ALUG/12+OVH/12+CLT for _ in range(12)]
for i in range(3,10):
    loja=C[i]*1000; cm=p[i]*TICKET; sob=p[i]*SOBRA
    base_sobra=loja-loja*CMV-loja*.154-fix_mes[i]
    nova=base_sobra+sob-cm*.154
    print(f"  {MES[i]:<6}{brl(loja):>12}{brl(cm):>12}{brl(loja+cm):>12}{pc(cm/loja,0):>10}"
          f"{brl(base_sobra)+' → '+brl(nova):>15}")
tri=(C[0]+C[1]+C[11])*1000
inv=[C[i]*1000+p[i]*TICKET for i in range(12)]
print(f"\n  Concentração em dez+jan+fev: {pc(tri/BASE,0)} → {pc((inv[0]+inv[1]+inv[11])/sum(inv),0)}")
print(f"  Média mensal de abr a out:   {brl(sum(C[3:10])*1000/7)} → {brl(sum(inv[3:10])/7)}")
print("  Os sete meses magros deixam de andar de lado. Era o ponto mais fraco do plano.")

print("\n"+"="*88); print("SENSIBILIDADE — 200 PARCEIROS"); print("="*88)
print(f"  {'Conversão por estadia':<26}{'Pedidos/ano':>13}{'Faturamento':>14}{'Ganho no lucro':>16}")
for cv in (.08,.12,.15,.20,.25):
    pd=[200*DIAS[i]*OCUP[i]/NOITES[i]*cv*(1+REPETE) for i in range(12)]
    f,l=lucro(sum(pd)*TICKET,sum(pd)*SOBRA)
    print(f"  {pc(cv,0)+(' (o plano)' if cv==CONV else ''):<26}{sum(pd):>13.0f}{brl(sum(pd)*TICKET):>14}{'+'+brl(l-l0):>16}")
print(f"\n  {'Comissão ao proprietário':<26}{'Sobra/caixa':>13}{'Ganho no lucro':>16}")
for cm_ in (.10,.15,.20,.25):
    s=TICKET-CUSTO-ENTREGA-TICKET*cm_
    p2=canal(200); f,l=lucro(sum(p2)*TICKET,sum(p2)*s)
    print(f"  {pc(cm_,0)+(' (o plano)' if cm_==COMISSAO else ''):<26}{brl(s,2):>13}{'+'+brl(l-l0):>16}")
