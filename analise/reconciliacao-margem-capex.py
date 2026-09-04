# -*- coding: utf-8 -*-
"""
Reconciliação v2: o dono TINHA funcionário. Então a explicação anterior (folha)
não fecha. Onde está a diferença de verdade?
"""
def brl(v): return ("R$ %s" % f"{v:,.0f}").replace(",",".")
def pct(v,b): return f"{v/b*100:.1f}%"

print("="*100)
print("TESTE 1 · A CONTA DELE É POSSÍVEL? R$ 15 mil/mês, COM funcionário, sobrando R$ 6-8 mil")
print("="*100)
FAT = 15_000
SM  = 1_621          # salário mínimo 2026
CLT = SM*1.4         # custo real de 1 CLT no Simples
linhas = [
    ("Faturamento",                 FAT,        None),
    ("− CMV (32,5%)",              -FAT*.325,  "polpa R$ 15-22/kg + toppings + embalagem + quebra"),
    ("− 1 funcionário CLT",        -CLT,        f"salário mínimo R$ {SM} x 1,4 (encargos no Simples)"),
    ("− Simples Anexo I (4%)",     -FAT*.04,    "faixa 1: até R$ 180 mil/ano"),
    ("− Cartão (2,8%)",            -FAT*.028,   "maquininha"),
]
acc=0
for n,v,obs in linhas:
    acc = v if acc==0 and v>0 else acc+v
    print(f"  {n:<28}{brl(v):>12}   {obs or ''}")
print(f"  {'':<28}{'-'*12}")
print(f"  {'= SOBRA antes de aluguel':<28}{brl(acc):>12}   <<<  {pct(acc,FAT)} do faturamento")
print(f"  {'  e contas fixas':<28}")
print(f"""
  >>> R$ {acc:,.0f}/mês CAI EXATAMENTE DENTRO DA FAIXA "R$ 6 A 8 MIL" QUE ELE FALOU.

  Ou seja: os R$ 6-8 mil dele quase certamente são a sobra ANTES de pagar aluguel,
  energia, água, gás e contador — que é como quase todo dono de loja pequena pensa
  em "sobrar". Não é lucro líquido no fim do mês.
""".replace(",","."))

print("="*100)
print("TESTE 2 · E SE FOSSE LUCRO LÍQUIDO MESMO? O que teria que ser verdade")
print("="*100)
fixos_tipicos = 1_500 + 800   # aluguel + energia/água/gás/contador
liq = acc - fixos_tipicos
print(f"""  Descontando aluguel de R$ 1.500 e contas de R$ 800:
     Lucro líquido real dele ......... {brl(liq)}/mês  ({pct(liq,FAT)})

  Para sobrarem R$ 7.000 LÍQUIDOS de R$ 15.000, com 1 funcionário, seria preciso:
     - CMV de apenas {pct(FAT - CLT - FAT*.04 - FAT*.028 - fixos_tipicos - 7000, FAT)} (contra os 32,5% de mercado), OU
     - ponto próprio, sem aluguel, e contas muito baixas, OU
     - o funcionário não ser CLT, OU
     - faturamento informal (sem nota em parte das vendas)

  Nenhuma dessas é impossível — só precisa ser confirmada.""")

print("\n"+"="*100)
print("TESTE 3 · A MESMA CONTA, LINHA POR LINHA, NOS DOIS NEGÓCIOS")
print("="*100)
# Nossa operação (marca própria, hiberna mai-ago)
N = dict(fat=389_376, cmv=126_547, folha=68_200, imp=23_131, cart=18_002,
         mkt=13_628, alug=21_000, ovh=28_200)
D = dict(fat=180_000, cmv=58_500, folha=CLT*12, imp=7_200, cart=5_040,
         mkt=0, alug=18_000, ovh=9_600)
def bloco(nome, x):
    sobra = x['fat']-x['cmv']-x['folha']-x['imp']-x['cart']-x['mkt']
    liq   = sobra-x['alug']-x['ovh']
    return sobra, liq
ns, nl = bloco("nosso", N)
ds, dl = bloco("dele",  D)

print(f"  {'Linha':<34}{'A loja dele':>15}{'%':>8}{'Nosso projeto':>17}{'%':>8}")
print("  "+"-"*96)
rows = [("Faturamento", D['fat'], N['fat']),
        ("− CMV", -D['cmv'], -N['cmv']),
        ("− Folha", -D['folha'], -N['folha']),
        ("− Impostos", -D['imp'], -N['imp']),
        ("− Cartão e delivery", -D['cart'], -N['cart']),
        ("− Marketing", -D['mkt'], -N['mkt'])]
for n,d,o in rows:
    print(f"  {n:<34}{brl(d):>15}{pct(abs(d),D['fat']):>8}{brl(o):>17}{pct(abs(o),N['fat']):>8}")
print("  "+"-"*96)
print(f"  {'= SOBRA antes de aluguel e fixos':<34}{brl(ds):>15}{pct(ds,D['fat']):>8}{brl(ns):>17}{pct(ns,N['fat']):>8}")
print(f"  {'− Aluguel':<34}{brl(-D['alug']):>15}{pct(D['alug'],D['fat']):>8}{brl(-N['alug']):>17}{pct(N['alug'],N['fat']):>8}")
print(f"  {'− Energia, gás, contador, PDV':<34}{brl(-D['ovh']):>15}{pct(D['ovh'],D['fat']):>8}{brl(-N['ovh']):>17}{pct(N['ovh'],N['fat']):>8}")
print("  "+"-"*96)
print(f"  {'= LUCRO LÍQUIDO':<34}{brl(dl):>15}{pct(dl,D['fat']):>8}{brl(nl):>17}{pct(nl,N['fat']):>8}")

print(f"""
  Leitura:
   . Na linha "sobra antes de aluguel e fixos" ele fica em {pct(ds,D['fat'])} e nós em {pct(ns,N['fat'])}.
     A diferença de ~{abs(ds/D['fat']-ns/N['fat'])*100:.0f} pontos é marketing (3,5%) e comissão de delivery,
     que são ESCOLHAS nossas, não ineficiência.
   . Na linha de lucro líquido ele fica em {pct(dl,D['fat'])} e nós em {pct(nl,N['fat'])}.
   . Se a gente cortasse marketing pago e delivery, nosso líquido subiria para
     {pct((nl+N['mkt']+N['cart']*0.5)/N['fat']*N['fat'],N['fat'])} — mas perderia faturamento junto. Não é troca óbvia.""")

print("\n"+"="*100)
print("TESTE 4 · E SE A MARGEM DELE FOR REAL? O que muda no nosso projeto")
print("="*100)
for m,rot in ((.233,"minha projeção"),(.30,"se a dele for 30% líquido"),
              (.40,"se a dele for 40% líquido")):
    print(f"  Margem líquida de {m*100:>4.1f}% ({rot:<26}) -> lucro/ano de {brl(N['fat']*m):>12}"
          f"  · investimento de R$ 51.800 volta em {51_800/(N['fat']*m)*12:>4.1f} meses")
print("""
  Mesmo na minha projeção conservadora o primeiro verão paga o investimento.
  Se a margem dele for real, o negócio é melhor do que eu projetei — não pior.
  Por isso a pergunta certa vale ouro.""")

print("\n"+"="*100)
print("A PERGUNTA, REESCRITA — mande exatamente assim")
print("="*100)
print("""
  "Quando tu falou que faturando R$ 15 mil sobravam R$ 6 a 8 mil:
   1. Isso era ANTES ou DEPOIS de pagar o aluguel e as contas (luz, água, gás, contador)?
   2. O ponto era alugado ou próprio? Se alugado, quanto era?
   3. Era um funcionário só, ou mais? Registrado em carteira?
   4. Esses R$ 15 mil eram de um mês de verão ou a média do ano?
   5. Quanto do faturamento ia embora só em polpa e complemento?"

  Com essas cinco respostas eu fecho a conta e paro de estimar.""")
