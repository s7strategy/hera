# -*- coding: utf-8 -*-
"""
Viabilidade — açaiteria na Praia da Ferrugem, Garopaba/SC   ·   v3
Ponto: nº 2956, ~35 m² fechados + pátio com deck sob pergolado.
Aluguel real: R$ 2.500 (dez–fev) e R$ 1.500 (mar–nov) = R$ 21.000/ano.

SITUAÇÃO REAL (v3):
  - NÃO há taxa de franquia nem royalty. O vínculo com a Degusta é de COMPRA
    de insumo — o único custo de usar a marca está embutido no CMV.
  - O equipamento JÁ FOI COMPRADO (unidade Degusta que quebrou, estado de nova).
    É custo afundado: não entra na decisão daqui para frente.
  - A decisão real: MANTER a plotagem Degusta e comprar deles
    vs. PLOTAR marca própria e comprar no mercado livre.
Valores em R$ correntes de 2026.
"""
MESES = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
DIAS  = [31,28,31,30,31,30,31,31,30,31,30,31]
PICO  = ("Jan","Fev")
CHEIO = ("Dez","Jan","Fev","Mar")          # meses de operação em capacidade
ALUGUEL_ALTO = ("Dez","Jan","Fev")         # R$ 2.500
AL_ALTO, AL_BAIXO = 2_500, 1_500

CLI  = [140,100,45,24,15,11,18,11,15,21,29,74]   # clientes/dia — ESTIMATIVA
TETO = 250                                        # teto físico do ponto

FAIXAS=[(180_000,.040,0),(360_000,.073,5_940),(720_000,.095,13_860),
        (1_800_000,.107,22_500),(3_600_000,.143,87_300),(4_800_000,.190,378_000)]
def aliq(r):
    for t,n,d in FAIXAS:
        if r<=t: return max((r*n-d)/r,0) if r else 0
    return .19
def brl(v): return ("R$ %s" % f"{v:,.0f}").replace(",",".")

class C:
    def __init__(s,nome,ticket,cmv,fluxo,capex,f_pico,f_cheio,f_baixa,mkt,ovh,fechado=()):
        d=dict(locals()); d.pop('s'); s.__dict__.update(d)

def dre(c,mult=1.0,cmv=None,teto=True):
    CMV = c.cmv if cmv is None else cmv
    cl=[min(x*c.fluxo*mult,TETO) if teto else x*c.fluxo*mult for x in CLI]
    cl=[p*d for p,d in zip(cl,DIAS)]
    rec=[0 if m in c.fechado else x*c.ticket for m,x in zip(MESES,cl)]
    fat=sum(rec); a=aliq(fat); L=[]
    for i,m in enumerate(MESES):
        r=rec[i]; off = m in c.fechado
        custo=r*CMV
        taxas=r*.028 + r*.12*.152
        imp=r*a
        alug=AL_ALTO if m in ALUGUEL_ALTO else AL_BAIXO
        folha=0 if off else (c.f_pico if m in PICO else c.f_cheio if m in CHEIO else c.f_baixa)
        ovh=c.ovh*(0.35 if off else 1.0)
        mkt=r*c.mkt
        lucro=r-custo-taxas-imp-alug-folha-ovh-mkt
        L.append(dict(m=m,r=r,cmv=custo,taxas=taxas,imp=imp,alug=alug,folha=folha,
                      ovh=ovh,mkt=mkt,lucro=lucro,cli=0 if off else cl[i]))
    return L,fat,a

def kpi(c,mult=1.0,**kw):
    L,fat,a=dre(c,mult,**kw); lu=sum(x["lucro"] for x in L)
    return dict(fat=fat,lucro=lu,marg=lu/fat if fat else 0,capex=c.capex,
                pb=c.capex/lu*12 if lu>0 else None,
                neg=sum(1 for x in L if x["lucro"]<0),
                burn=-sum(x["lucro"] for x in L if x["lucro"]<0),L=L)

# ---------------------------------------------------------------- CENÁRIOS
# CAPEX = só o que falta gastar. Equipamento já comprado NÃO entra.
#   obra/adequação 35m² + pia VISA .... 22.000
#   abrir a tela e ajustar o deck ......  7.000
#   mobiliário do deck ................. 11.000
#   estoque inicial ....................  9.000
#   licenças (alvará, VISA, INMETRO) ...  3.000
#   marketing de abertura ..............  6.000
#   capital de giro .................... 28.000
#   ------------------------------------------
#   base comum ......................... 86.000
BASE = 86_000
PLOTAGEM = 22_000   # identidade própria: marca+INPI, fachada, plotagem de equipamento,
                    # copos e embalagens personalizados, sinalização do deck

DEG = C("A · Mantém Degusta (compra insumo deles)", 27,.385,1.00, BASE,
        16_000,10_500,3_800, .020,3_000)
PRO = C("B · Plota marca própria (compra livre)",   32,.325,.90,  BASE+PLOTAGEM,
        16_000,10_500,3_800, .035,3_000)
PRO_H = C("B2 · Marca própria — hiberna mai–ago",   32,.325,.90,  BASE+PLOTAGEM,
        16_000,10_500,3_800, .035,3_000, fechado=("Mai","Jun","Jul","Ago"))
DEG_H = C("A2 · Degusta — hiberna mai–ago",         27,.385,1.00, BASE,
        16_000,10_500,3_800, .020,3_000, fechado=("Mai","Jun","Jul","Ago"))

print("="*104)
print("PARTE 1 · A CONTA COM O ALUGUEL REAL (R$ 2.500 dez–fev · R$ 1.500 mar–nov = R$ 21.000/ano)")
print("="*104)
for c in (DEG_H,PRO_H):
    L,fat,a=dre(c)
    print(f"\n### {c.nome}")
    print(f"    Ticket R$ {c.ticket:.2f} | CMV {c.cmv*100:.1f}% | Simples {a*100:.2f}% | Falta investir {brl(c.capex)}")
    print(f"    {'Mês':<5}{'Cli':>7}{'Receita':>11}{'CMV':>10}{'Folha':>9}{'Aluguel':>9}{'Imposto':>9}{'LUCRO':>11}")
    for l in L:
        print(f"    {l['m']:<5}{l['cli']:>7,.0f}{l['r']:>11,.0f}{-l['cmv']:>10,.0f}{-l['folha']:>9,.0f}"
              f"{-l['alug']:>9,.0f}{-l['imp']:>9,.0f}{l['lucro']:>11,.0f}")
    lu=sum(x['lucro'] for x in L)
    print(f"    {'ANO':<5}{sum(x['cli'] for x in L):>7,.0f}{fat:>11,.0f}{-sum(x['cmv'] for x in L):>10,.0f}"
          f"{-sum(x['folha'] for x in L):>9,.0f}{-sum(x['alug'] for x in L):>9,.0f}"
          f"{-sum(x['imp'] for x in L):>9,.0f}{lu:>11,.0f}")
    k=kpi(c)
    print(f"    -> Margem {k['marg']*100:.1f}% | Payback do que falta investir: "
          f"{('%.0f meses'%k['pb']) if k['pb'] else 'nunca'} | Meses no vermelho: {k['neg']}")

print("\n"+"="*104)
print("PARTE 2 · COMPARATIVO")
print("="*104)
print(f"{'Caminho':<44}{'Falta investir':>16}{'Faturam.':>12}{'Lucro/ano':>12}{'Margem':>9}{'Payback':>10}")
print("-"*104)
for c in (DEG,DEG_H,PRO,PRO_H):
    k=kpi(c); pb=f"{k['pb']:.0f} m" if k['pb'] else "nunca"
    print(f"{c.nome:<44}{brl(c.capex):>16}{brl(k['fat']):>12}{brl(k['lucro']):>12}{k['marg']*100:>8.1f}%{pb:>10}")

print("\n"+"="*104)
print("PARTE 3 · A ÚNICA PERGUNTA QUE IMPORTA AGORA")
print("       Sem taxa e sem royalty, usar a marca Degusta custa APENAS o markup do insumo.")
print("       Quanto o insumo deles precisa ser mais caro para valer a pena plotar marca própria?")
print("="*104)
base_livre = .325
print(f"{'CMV Degusta':>14}{'Markup vs livre':>18}{'Lucro Degusta':>16}{'Lucro própria':>16}{'Diferença':>14}   Veredito")
print("-"*104)
lucro_pro = kpi(PRO_H)['lucro']
for cmvd in (.325,.34,.355,.37,.385,.40,.42):
    ld = kpi(DEG_H, cmv=cmvd)['lucro']
    mk = (cmvd-base_livre)/base_livre*100
    print(f"{cmvd*100:>13.1f}%{mk:>17.0f}%{brl(ld):>16}{brl(lucro_pro):>16}"
          f"{brl(lucro_pro-ld):>14}   {'PLOTAR PRÓPRIA' if lucro_pro>ld else 'MANTER DEGUSTA'}")

print(f"""
  Leitura: a marca própria carrega {brl(PLOTAGEM)} de investimento a mais e ganha ticket maior
  (R$ 32 vs R$ 27) com CMV menor. Se a Degusta vender insumo a preço de mercado, o
  cálculo depende só do ticket. Se vender com markup, a conta abre rápido.""")

print("\n"+"="*104)
print("PARTE 4 · E SE O TICKET DA DEGUSTA FOR IGUAL AO DA MARCA PRÓPRIA?")
print("       (isola o efeito do insumo, tirando a vantagem de posicionamento)")
print("="*104)
print(f"{'Ticket':>10}{'CMV Degusta':>14}{'Degusta':>14}{'Própria':>14}{'Diferença':>14}")
print("-"*104)
for t in (27,30,32):
    d=C("d",t,.385,1.00,BASE,16_000,10_500,3_800,.020,3_000,fechado=("Mai","Jun","Jul","Ago"))
    p=C("p",t,.325,1.00,BASE+PLOTAGEM,16_000,10_500,3_800,.035,3_000,fechado=("Mai","Jun","Jul","Ago"))
    ld,lp=kpi(d)['lucro'],kpi(p)['lucro']
    print(f"R$ {t:>7}{'38,5%':>14}{brl(ld):>14}{brl(lp):>14}{brl(lp-ld):>14}")

print("\n"+"="*104)
print("PARTE 5 · PAYBACK DA PLOTAGEM — em quanto tempo a marca própria se paga sozinha")
print("="*104)
for cmvd in (.34,.355,.385,.40):
    ld=kpi(DEG_H,cmv=cmvd)['lucro']; dif=lucro_pro-ld
    if dif>0:
        print(f"  Se a Degusta cobrar CMV de {cmvd*100:.1f}% -> ganho de {brl(dif)}/ano  "
              f"->  {brl(PLOTAGEM)} de plotagem se pagam em {PLOTAGEM/dif*12:.1f} meses")
    else:
        print(f"  Se a Degusta cobrar CMV de {cmvd*100:.1f}% -> marca própria perde {brl(-dif)}/ano — manter Degusta")

print("\n"+"="*104)
print("PARTE 6 · SENSIBILIDADE AO FLUXO (a premissa que continua sendo a mais frágil)")
print("="*104)
print(f"{'Cenário':<28}{'Cli/dia jan':>13}{'Degusta':>16}{'Marca própria':>18}")
print("-"*104)
for nome,m in [("Pessimista (−35%)",.65),("Conservador (−15%)",.85),("Base",1.00),
               ("Otimista (+25%)",1.25),("No teto do ponto",1.79)]:
    print(f"{nome:<28}{min(140*m,TETO):>13.0f}{brl(kpi(DEG_H,m)['lucro']):>16}{brl(kpi(PRO_H,m)['lucro']):>18}")

print("\n"+"="*104)
print("PARTE 7 · PONTO DE EQUILÍBRIO com o aluguel real")
print("="*104)
for c in (DEG,DEG_H,PRO,PRO_H):
    lo,hi=.02,6.0
    for _ in range(90):
        mid=(lo+hi)/2
        if kpi(c,mid)['lucro']<0: lo=mid
        else: hi=mid
    print(f"{c.nome:<44} empata com {hi*100:>5.0f}% do fluxo base  (≈{min(hi*140,TETO):>3.0f} clientes/dia em janeiro)")
