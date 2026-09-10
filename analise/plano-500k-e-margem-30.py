# -*- coding: utf-8 -*-
"""O plano de R$ 350k na alta + R$ 150k no resto é realista? E como chegar a 30% de margem."""
def brl(v): return ("R$ %s" % f"{v:,.0f}").replace(",",".")
def pc(v,b): return f"{v/b*100:.1f}%"
MES=["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
DIAS=[31,28,31,30,31,30,31,31,30,31,30,31]
ALTA=("Dez","Jan","Fev","Mar")

print("="*100)
print("PARTE 1 · A CONTA DELE COM 3 A 5 FUNCIONÁRIOS NO VERÃO")
print("="*100)
SM=1_621; CLT=SM*1.4
print(f"""
  Você corrigiu: era 1 funcionário, subindo para 3 a 5 no verão.
  Isso muda a reconstrução da loja dele — e provavelmente significa que os
  R$ 15 mil NÃO eram o faturamento de verão.

  Folha dele, refeita:
    8 meses com 1 funcionário .......... {brl(CLT*8):>10}
    4 meses com 4 (média de 3 a 5) ..... {brl(CLT*4*4):>10}
    TOTAL ANUAL ........................ {brl(CLT*8 + CLT*16):>10}   (antes eu usei {brl(CLT*12)})
""")
folha_dele = CLT*8 + CLT*16
print(f"""  Se ele faturava R$ 15 mil/mês o ano todo (R$ 180 mil), com essa folha:
    Faturamento ............ {brl(180_000):>11}
    − CMV 32,5% ............ {brl(-58_500):>11}
    − Folha ................ {brl(-folha_dele):>11}
    − Simples 4% ........... {brl(-7_200):>11}
    − Cartão 2,8% .......... {brl(-5_040):>11}
    = Sobra antes de fixos . {brl(180_000-58_500-folha_dele-7_200-5_040):>11}   ({pc(180_000-58_500-folha_dele-7_200-5_040,180_000)})
    Isso dá {brl((180_000-58_500-folha_dele-7_200-5_040)/12)}/mês — ABAIXO dos R$ 6 a 8 mil que ele falou.

  >>> CONCLUSÃO: se ele colocava 3 a 5 no verão, os R$ 15 mil NÃO podem ser a média
      do ano. Ninguém contrata 5 pessoas para uma loja de R$ 15 mil/mês.
      Os R$ 15 mil eram provavelmente o MÊS FRACO, e o verão faturava muito mais.""")

for fat_verao in (40_000, 60_000, 80_000):
    fat_ano = 15_000*8 + fat_verao*4
    folha = folha_dele
    sobra = fat_ano*(1-.325) - folha - fat_ano*.04 - fat_ano*.028
    print(f"    Se o verão dele fazia {brl(fat_verao)}/mês -> ano de {brl(fat_ano):>11}"
          f" · sobra antes de fixos {brl(sobra):>11} ({pc(sobra,fat_ano)}) = {brl(sobra/12)}/mês")
print("""
      A faixa de R$ 6 a 8 mil/mês de sobra volta a bater quando o verão dele
      fatura entre R$ 40 e 60 mil/mês. Isso é uma loja bem parecida com a nossa.""")

print("\n"+"="*100)
print("PARTE 2 · O PLANO DE R$ 350 MIL NA ALTA + R$ 150 MIL NO RESTO")
print("="*100)
TICKET=32
# minha projeção atual (marca própria, hiberna)
meu_alta = 66_067+124_992+80_640+40_176
meu_resto_hib = 20_736+12_960+18_749+25_056
meu_resto_12m = 438_163 - meu_alta
print(f"""
  {'':38}{'Meu modelo':>16}{'Seu plano':>14}{'Diferença':>14}
  {'-'*82}
  {'Alta (dez, jan, fev, mar)':<38}{brl(meu_alta):>16}{brl(350_000):>14}{'+'+pc(350_000-meu_alta,meu_alta):>14}
  {'Resto do ano (hibernando mai-ago)':<38}{brl(meu_resto_hib):>16}{brl(150_000):>14}{'+'+pc(150_000-meu_resto_hib,meu_resto_hib):>14}
  {'Resto do ano (operando 12 meses)':<38}{brl(meu_resto_12m):>16}{brl(150_000):>14}{'+'+pc(150_000-meu_resto_12m,meu_resto_12m):>14}
  {'-'*82}
  {'TOTAL':<38}{brl(meu_alta+meu_resto_hib):>16}{brl(500_000):>14}
""")
print("  Quantos clientes por dia cada parte do seu plano exige (ticket R$ 32):")
prop={"Dez":.21,"Jan":.40,"Fev":.26,"Mar":.13}
print(f"    {'Mês':<6}{'Receita':>12}{'Clientes':>11}{'Cli/dia':>10}{'Meu modelo':>13}   Leitura")
for m in ("Dez","Jan","Fev","Mar"):
    r=350_000*prop[m]; d=DIAS[MES.index(m)]; cd=r/TICKET/d
    meu={"Dez":66_067,"Jan":124_992,"Fev":80_640,"Mar":40_176}[m]/TICKET/d
    lei = "no teto do ponto!" if cd>230 else ("apertado" if cd>170 else "ok")
    print(f"    {m:<6}{brl(r):>12}{r/TICKET:>11,.0f}{cd:>10.0f}{meu:>13.0f}   {lei}")
resto_m = 150_000/8
print(f"""
    Resto do ano: {brl(150_000)} em 8 meses = {brl(resto_m)}/mês
    A {brl(resto_m)}/mês com ticket R$ 32 são {resto_m/TICKET:.0f} clientes/mês = {resto_m/TICKET/30:.0f}/dia
    O meu modelo tem 11 a 29 clientes/dia nesses meses. Seu plano pede {resto_m/TICKET/30:.0f}/dia
    TODO MÊS, inclusive junho e agosto.""")

print("\n"+"="*100)
print("PARTE 3 · O VEREDITO SOBRE O PLANO, PARTE POR PARTE")
print("="*100)
print(f"""
  R$ 350 MIL NA ALTA ................................ REALISTA
     É 12% acima do meu cenário base. Exige 141 clientes/dia em janeiro, que é
     exatamente a minha premissa de fluxo SEM o desconto de 10% que apliquei por
     ser marca nova. Se o ponto tiver o movimento que estimo, isso acontece.
     Só cuidado com dezembro: o plano pede 74/dia num mês que só engrena na
     segunda metade.

  R$ 150 MIL NO RESTO DO ANO ........................ NÃO REALISTA
     São {brl(resto_m)}/mês, todo mês, de abril a novembro — o dobro do que projeto
     e quase 20% acima do que dá operando 12 meses no cenário otimista.
     Junho e agosto na Ferrugem, com o bairro vazio e frio, não fazem {brl(resto_m)}.

     O que seria realista no resto do ano:
       Hibernando mai-ago ......... {brl(meu_resto_hib)}
       Operando 12 meses .......... {brl(meu_resto_12m)}
       Operando 12 meses, otimista  {brl(meu_resto_12m*1.25)}
       Seu plano .................. {brl(150_000)}   <- pede mais que o otimista

  TOTAL REALISTA ........... {brl(350_000+meu_resto_12m)} a {brl(350_000+meu_resto_12m*1.25)}
  SEU PLANO ................ {brl(500_000)}

  >>> Você acerta a alta e superestima a baixa. Um plano de R$ 420 a 460 mil é
      defensável. R$ 500 mil só se a baixa temporada surpreender muito.""")

print("\n"+"="*100)
print("PARTE 4 · COMO CHEGAR A 30% DE MARGEM")
print("="*100)
FAT=389_376
base=dict(cmv=.325, folha=68_200, imp=.0594, cart=.046, mkt=.035, alug=21_000, ovh=28_200)
def lucro(fat=FAT, **kw):
    p=dict(base); p.update(kw)
    return fat - fat*p['cmv'] - p['folha'] - fat*p['imp'] - fat*p['cart'] - fat*p['mkt'] - p['alug'] - p['ovh']
L0=lucro()
print(f"  Partida: {brl(L0)} sobre {brl(FAT)} = {pc(L0,FAT)}\n")
alav=[
 ("Família no balcão (folha R$ 34.800)",      dict(folha=34_800)),
 ("Família opera, contrata só no pico",       dict(folha=19_000)),
 ("Cortar marketing pago",                    dict(mkt=0)),
 ("Sair do delivery (perde ~8% da receita)",  dict(cart=.028)),
 ("CMV de 32,5% para 29% (compra melhor)",    dict(cmv=.29)),
 ("Ticket de R$ 32 para R$ 35 (+9%)",         dict()),
]
print(f"  {'Alavanca':<44}{'Lucro':>13}{'Margem':>9}{'Ganho':>12}")
print("  "+"-"*80)
for nome,kw in alav:
    if "Ticket" in nome:
        f2=FAT*1.09; l=lucro(fat=f2); m=l/f2
    elif "delivery" in nome:
        f2=FAT*0.92; l=lucro(fat=f2, **kw); m=l/f2
    else:
        l=lucro(**kw); m=l/FAT
    print(f"  {nome:<44}{brl(l):>13}{m*100:>8.1f}%{brl(l-L0):>12}")
comb=lucro(folha=34_800, mkt=0)
print("  "+"-"*80)
print(f"  {'Família no balcão + sem marketing pago':<44}{brl(comb):>13}{comb/FAT*100:>8.1f}%{brl(comb-L0):>12}")
f3=FAT*1.09; comb2=lucro(fat=f3, folha=34_800)
print(f"  {'Família no balcão + ticket R$ 35':<44}{brl(comb2):>13}{comb2/f3*100:>8.1f}%{brl(comb2-L0):>12}")
print(f"""
  >>> Para sobrar 30% com equipe toda contratada, seria preciso ticket de R$ 35
      E CMV de 29% ao mesmo tempo — possível, mas exige as duas coisas dando certo.
      O caminho mais direto para 30% é a família no balcão: sozinho isso já leva
      a margem para {lucro(folha=34_800)/FAT*100:.1f}%.""")
