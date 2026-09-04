# -*- coding: utf-8 -*-
"""
Viabilidade — açaiteria na Praia da Ferrugem, Garopaba/SC
Ponto real: ~35 m² fechados + pátio com deck sob pergolado. Nº 2956.
Compara: (A) Franquia Degusta Açaí (Ijuí/RS)  vs  (B) Marca própria elevada.
Negócio autônomo — sem relação com nenhum outro projeto.
Valores em R$ correntes de 2026.
"""
MESES = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
DIAS  = [31,28,31,30,31,30,31,31,30,31,30,31]
ALTA  = ("Dez","Jan","Fev","Mar")
PICO  = ("Jan","Fev")

# Curva de demanda (clientes/dia). Calibrada para rua de pousadas da Ferrugem,
# NÃO para o calçadão de bares. Premissa a validar em campo — ver PARTE 7.
CLI = [140,100,45,24,15,11,18,11,15,21,29,74]

# TETO FÍSICO DO PONTO: 35 m² com balcão self-service de ~3,5 m + deck.
# 2 balanças processam ~60-70 clientes/hora; o gargalo real é fila e assento.
TETO_DIA = 250

FAIXAS=[(180_000,.040,0),(360_000,.073,5_940),(720_000,.095,13_860),
        (1_800_000,.107,22_500),(3_600_000,.143,87_300),(4_800_000,.190,378_000)]
def aliq(r):
    for t,n,d in FAIXAS:
        if r<=t: return max((r*n-d)/r,0) if r else 0
    return .19
def brl(v): return ("R$ %s" % f"{v:,.0f}").replace(",",".")

class C:
    def __init__(s,nome,ticket,cmv,fluxo,capex,roy_mes,mkt_rede,
                 al_alta,al_baixa,f_pico,f_alta,f_baixa,mkt,ovh,fechado=(),curto=""):
        d=dict(locals()); d.pop('s'); s.__dict__.update(d)

def dre(c,mult=1.0,al_alta=None,al_baixa=None,teto=True):
    aa = c.al_alta if al_alta is None else al_alta
    ab = c.al_baixa if al_baixa is None else al_baixa
    cl=[]
    for x,d in zip(CLI,DIAS):
        por_dia = x*c.fluxo*mult
        if teto: por_dia = min(por_dia, TETO_DIA)   # o ponto não estica
        cl.append(por_dia*d)
    rec=[0 if m in c.fechado else x*c.ticket for m,x in zip(MESES,cl)]
    fat=sum(rec); a=aliq(fat); L=[]
    for i,m in enumerate(MESES):
        r=rec[i]; off = m in c.fechado
        cmv=r*c.cmv
        taxas=r*.028 + r*.12*.152                    # cartão + iFood sobre ~12% da receita
        imp=r*a
        alug=(aa if m in ALTA else ab)               # aluguel corre mesmo fechado
        folha=0 if off else (c.f_pico if m in PICO else c.f_alta if m in ALTA else c.f_baixa)
        ovh=c.ovh*(0.35 if off else 1.0)
        roy=(0 if off and c.roy_mes else c.roy_mes)+r*c.mkt_rede
        mkt=r*c.mkt
        lucro=r-cmv-taxas-imp-alug-folha-ovh-roy-mkt
        L.append(dict(m=m,r=r,cmv=cmv,taxas=taxas,imp=imp,alug=alug,folha=folha,
                      ovh=ovh,roy=roy,mkt=mkt,lucro=lucro,cli=0 if off else cl[i]))
    return L,fat,a

def kpi(c,mult=1.0,**kw):
    L,fat,a=dre(c,mult,**kw); lu=sum(x["lucro"] for x in L)
    return dict(nome=c.nome,fat=fat,lucro=lu,marg=lu/fat if fat else 0,aliq=a,
                pb=c.capex/lu*12 if lu>0 else None, capex=c.capex,
                neg=sum(1 for x in L if x["lucro"]<0),
                burn=-sum(x["lucro"] for x in L if x["lucro"]<0),
                roy=sum(x["roy"] for x in L), L=L)

# ------------------------------------------------------------------ CENÁRIOS
FORA=("Abr","Mai","Jun","Jul","Ago","Set","Out")

A  = C("A · Franquia Degusta — 12 meses",          27,.385,1.00,195_000,2_000,.02,
       3_000,2_200, 17_000,11_000,4_500, .015,3_400)
A2 = C("A2 · Franquia Degusta — enxuta na baixa",  27,.385,1.00,195_000,2_000,.02,
       3_000,2_200, 17_000,10_000,3_400, .015,3_000)
B  = C("B · Marca própria elevada — 12 meses",     32,.325,.90,155_000,0,0,
       3_000,2_200, 17_000,11_000,4_000, .035,3_200)
B2 = C("B2 · Marca própria — hiberna mai–ago",     32,.325,.90,155_000,0,0,
       3_000,2_200, 17_000,11_000,4_000, .035,3_200, fechado=("Mai","Jun","Jul","Ago"))
B3 = C("B3 · Marca própria — só temporada nov–mar",32,.325,.90,132_000,0,0,
       3_000,2_200, 17_000,10_500,0,     .035,3_000, fechado=FORA)

print("="*106)
print("PARTE 1 · DRE MÊS A MÊS — os dois caminhos principais")
print("="*106)
for c in (A2,B2):
    L,fat,a=dre(c)
    print(f"\n### {c.nome}")
    print(f"    Ticket R$ {c.ticket:.2f} | CMV {c.cmv*100:.1f}% | Simples efetivo {a*100:.2f}% | CAPEX {brl(c.capex)}")
    print(f"    {'Mês':<5}{'Cli':>7}{'Receita':>11}{'CMV':>10}{'Folha':>9}{'Aluguel':>9}{'Royal.':>8}{'Imposto':>9}{'LUCRO':>11}")
    for l in L:
        print(f"    {l['m']:<5}{l['cli']:>7,.0f}{l['r']:>11,.0f}{-l['cmv']:>10,.0f}{-l['folha']:>9,.0f}"
              f"{-l['alug']:>9,.0f}{-l['roy']:>8,.0f}{-l['imp']:>9,.0f}{l['lucro']:>11,.0f}")
    lu=sum(x['lucro'] for x in L)
    print(f"    {'ANO':<5}{sum(x['cli'] for x in L):>7,.0f}{fat:>11,.0f}{-sum(x['cmv'] for x in L):>10,.0f}"
          f"{-sum(x['folha'] for x in L):>9,.0f}{-sum(x['alug'] for x in L):>9,.0f}"
          f"{-sum(x['roy'] for x in L):>8,.0f}{-sum(x['imp'] for x in L):>9,.0f}{lu:>11,.0f}")
    k=kpi(c)
    print(f"    -> Margem {k['marg']*100:.1f}% | Payback {('%.0f m'%k['pb']) if k['pb'] else 'nunca'} | "
          f"Meses no vermelho: {k['neg']} | Caixa queimado na baixa: {brl(k['burn'])}")

print("\n"+"="*106)
print("PARTE 2 · COMPARATIVO DOS CAMINHOS")
print("="*106)
print(f"{'Caminho':<44}{'CAPEX':>11}{'Faturam.':>12}{'Lucro/ano':>12}{'Margem':>9}{'Payback':>10}{'ROI':>8}")
print("-"*106)
for c in (A,A2,B,B2,B3):
    k=kpi(c); pb=f"{k['pb']:.0f} m" if k['pb'] else "nunca"
    print(f"{c.nome:<44}{brl(c.capex):>11}{brl(k['fat']):>12}{brl(k['lucro']):>12}"
          f"{k['marg']*100:>8.1f}%{pb:>10}{k['lucro']/c.capex*100:>7.0f}%")

print("\n"+"="*106)
print("PARTE 3 · SENSIBILIDADE AO FLUXO (a premissa mais frágil do estudo)")
print("="*106)
print(f"{'Cenário':<30}{'Cli/dia jan':>13}{'Franquia':>16}{'Própria hiberna':>18}{'Própria temporada':>20}")
print("-"*106)
for nome,m in [("Pessimista (−35%)",.65),("Conservador (−15%)",.85),("Base",1.00),
               ("Otimista (+25%)",1.25),("No teto do ponto (+79%)",1.79)]:
    cd=min(140*m,TETO_DIA)
    row=f"{nome:<30}{cd:>13.0f}"
    for c in (A2,B2,B3): row+=f"{brl(kpi(c,m)['lucro']):>16}" if c is A2 else f"{brl(kpi(c,m)['lucro']):>18}" if c is B2 else f"{brl(kpi(c,m)['lucro']):>20}"
    print(row)

print("\n"+"="*106)
print("PARTE 4 · PONTO DE EQUILÍBRIO")
print("="*106)
for c in (A,A2,B,B2,B3):
    lo,hi=.05,6.0
    for _ in range(90):
        mid=(lo+hi)/2
        if kpi(c,mid)['lucro']<0: lo=mid
        else: hi=mid
    k=kpi(c,hi)
    viavel = "" if hi*140<=TETO_DIA else "  << ACIMA DO TETO FÍSICO DO PONTO"
    print(f"{c.nome:<44} precisa de {hi*100:>5.0f}% do fluxo base "
          f"(≈{min(hi*140,TETO_DIA):>3.0f} cli/dia em jan · faturamento {brl(k['fat'])}){viavel}")

print("\n"+"="*106)
print("PARTE 5 · TESTE ADVERSARIAL — em que condições a FRANQUIA vence?")
print("="*106)
REF = kpi(B2)['lucro']
print(f"Referência: marca própria (hiberna mai–ago) entrega {brl(REF)}/ano.\n")

print("5.1 · Se o insumo da franqueadora não tivesse markup nenhum")
for cmv in (.30,.325,.34,.36,.385):
    c=C("f",27,cmv,1.00,195_000,2_000,.02,3_000,2_200,17_000,10_000,3_400,.015,3_000)
    l=kpi(c)['lucro']
    print(f"     CMV {cmv*100:>5.1f}% -> {brl(l):>12}   {'FRANQUIA VENCE' if l>REF else 'própria vence'}")

print("\n5.2 · Se o royalty fosse o mais baixo do mercado")
for roy in (0,1_160,1_500,2_000,3_000):
    c=C("f",27,.385,1.00,195_000,roy,.02,3_000,2_200,17_000,10_000,3_400,.015,3_000)
    l=kpi(c)['lucro']
    print(f"     Royalty {brl(roy):>10}/mês -> {brl(l):>12}   {'FRANQUIA VENCE' if l>REF else 'própria vence'}")

print("\n5.3 · Se a marca puxasse mais gente — o único caminho da franquia")
for ex in (0,.10,.20,.30,.40,.50,.60,.79):
    c=C("f",27,.385,1.00+ex,195_000,2_000,.02,3_000,2_200,17_000,10_000,3_400,.015,3_000)
    l=kpi(c)['lucro']; cd=min(140*(1+ex),TETO_DIA)
    teto = "  << no teto do ponto" if 140*(1+ex)>=TETO_DIA*0.95 else ""
    print(f"     +{ex*100:>3.0f}% ({cd:>3.0f} cli/dia jan) -> {brl(l):>12}   "
          f"{'FRANQUIA VENCE' if l>REF else 'própria vence'}{teto}")

print("\n5.4 · Mesmo ticket dos dois lados — custo puro de ser franqueado")
for t in (25,27,30,32,36):
    f=C("f",t,.385,1.00,195_000,2_000,.02,3_000,2_200,17_000,10_000,3_400,.015,3_000)
    p=C("p",t,.325,1.00,155_000,0,0,     3_000,2_200,17_000,11_000,4_000,.035,3_200)
    lf,lp=kpi(f)['lucro'],kpi(p)['lucro']
    print(f"     Ticket R$ {t}: franquia {brl(lf):>12} | própria {brl(lp):>12} | custo de franquear {brl(lp-lf)}")

print("\n"+"="*106)
print("PARTE 6 · SENSIBILIDADE AO ALUGUEL (35 m² + deck — valor ainda a negociar)")
print("="*106)
print(f"{'Aluguel alta / baixa':<28}{'Franquia':>18}{'Própria hiberna':>20}{'Própria temporada':>20}")
print("-"*106)
for aa,ab in ((2_000,1_500),(3_000,2_200),(4_000,3_000),(5_500,4_000),(7_000,5_000)):
    row=f"R$ {aa:,} / {ab:,}".replace(",",".").ljust(28)
    for c in (A2,B2,B3):
        row+=f"{brl(kpi(c,al_alta=aa,al_baixa=ab)['lucro']):>{18 if c is A2 else 20}}"
    print(row)

print("\n"+"="*106)
print("PARTE 7 · O QUE PRECISA SER MEDIDO")
print("="*106)
print(f"""  A curva parte de {CLI[0]} clientes/dia em janeiro. É ESTIMATIVA, não medição — e as fotos
  mostram uma rua de pousadas e casas, com paver e grama, não o calçadão de bares.
  Isso é o que mais pode derrubar (ou salvar) o negócio.

  Conversão de calçada para açaí em praia: 3% a 6% do fluxo pedestre.
  Para {CLI[0]} clientes/dia em janeiro são necessários 2.300 a 4.700 pedestres/dia na porta.

  Teto físico do ponto (35 m² + deck): ~{TETO_DIA} clientes/dia.
  Faturamento máximo teórico em janeiro: {brl(TETO_DIA*31*32)} (marca própria, ticket R$ 32).""")
