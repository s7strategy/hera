# -*- coding: utf-8 -*-
"""Reconciliação: de onde vem a margem, e por que a minha era 23% e a dele 40-50%."""
def brl(v): return ("R$ %s" % f"{v:,.0f}").replace(",",".")

FAT_PRO, LUCRO_PRO, FOLHA = 389_376, 90_665, 68_200
FAT_DEG, LUCRO_DEG        = 365_040, 62_101

print("="*98)
print("PARTE 1 · POR QUE A MINHA MARGEM DEU 23% E A DELE 40–50%")
print("="*98)
print("""
O dono comentou: faturando R$ 15 mil, sobravam R$ 6 a 8 mil  ->  40% a 53%.
Meu modelo deu 17% a 23%. Não é contradição — são duas contas diferentes.
A diferença tem UM nome só: FOLHA DE PAGAMENTO.
""")
for nome,fat,lu in (("Marca própria",FAT_PRO,LUCRO_PRO),("Mantém Degusta",FAT_DEG,LUCRO_DEG)):
    sem = lu + FOLHA
    print(f"  {nome}")
    print(f"    Faturamento .......................... {brl(fat)}")
    print(f"    Lucro COM equipe contratada .......... {brl(lu):>12}   margem {lu/fat*100:>5.1f}%   <- o meu número")
    print(f"    + folha de volta ..................... {brl(FOLHA):>12}")
    print(f"    Lucro SEM folha (dono opera) ......... {brl(sem):>12}   margem {sem/fat*100:>5.1f}%   <- o número dele\n")

print("""  Ou seja: os 40–50% que ele ouviu são de uma operação FAMILIAR, em que o dono
  e a família estão atrás do balcão e o próprio trabalho não aparece como custo.
  Os 17–23% do meu modelo são de uma operação com equipe CLT contratada.
  As duas contas estão certas. Só respondem perguntas diferentes.""")

print("\n"+"="*98)
print("PARTE 2 · O CENÁRIO QUE PROVAVELMENTE É O SEU: FAMÍLIA NO BALCÃO")
print("="*98)
# Estrutura de folha atual (equipe 100% contratada)
print("""
  Folha modelada até aqui (100% contratada, com encargos do Simples):
    Jan e Fev (pico) .... R$ 16.000/mês  ~ 5 pessoas
    Dez e Mar ........... R$ 10.500/mês  ~ 3-4 pessoas
    Set a Nov / Abr ..... R$  3.800/mês  ~ 1-2 pessoas
    Total ............... R$ 68.200/ano
""")
CEN = [
 ("A · Tudo contratado (o que modelei)",      16_000,10_500,3_800),
 ("B · Você e mais um da família no balcão",   9_500, 5_500,1_200),
 ("C · Família opera, contrata só no pico",    6_500, 3_000,    0),
]
MESES_PICO, MESES_CHEIO, MESES_BAIXA = 2, 2, 4   # jan-fev / dez-mar / set-nov+abr (hiberna mai-ago)
print(f"  {'Cenário de equipe':<42}{'Folha/ano':>12}{'Lucro própria':>15}{'Margem':>9}{'Payback*':>10}")
print("  "+"-"*94)
INVEST_REAL = 52_000   # ver PARTE 3
for nome,p,c,b in CEN:
    folha = p*MESES_PICO + c*MESES_CHEIO + b*MESES_BAIXA
    lucro = LUCRO_PRO + (FOLHA - folha)
    print(f"  {nome:<42}{brl(folha):>12}{brl(lucro):>15}{lucro/FAT_PRO*100:>8.1f}%"
          f"{INVEST_REAL/lucro*12:>9.1f}m")
print("""
  *Payback sobre R$ 52 mil de investimento real (ver Parte 3), não sobre os R$ 86 mil
   que eu tinha colocado antes.

  ATENÇÃO: no cenário C o seu trabalho e o do seu pai valem dinheiro e não estão
  na conta. Se vocês tirassem R$ 4 mil/mês cada um nos 5 meses de operação, seriam
  R$ 40 mil — que sairiam desse lucro. Não é errado fazer assim; só não confunda
  'lucro do negócio' com 'lucro depois de me pagar'.""")

print("\n"+"="*98)
print("PARTE 3 · O CAPEX — ONDE EU ERREI, COM O DEDO NA FERIDA")
print("="*98)
antes = [
 ("Obra e adequação dos 35 m²",           22_000,  9_000, "Elétrica p/ freezers e balcão, pia da Vigilância, piso lavável. Inflei: se o ponto está em bom estado, é metade"),
 ("Abrir a tela do deck",                  7_000,  1_500, "ERREI FEIO. Tirar tela e mourão é serviço de meio dia"),
 ("Mobiliário do deck",                   11_000,  6_000, "8 mesas + 24 cadeiras. Se veio no lote da unidade, é ZERO"),
 ("Estoque inicial",                       9_000,  9_000, "Esse é real e você já apontou"),
 ("Licenças (alvará, VISA, balança)",      3_000,  1_800, "Se a balança INMETRO veio no lote, cai para ~R$ 800"),
 ("Marketing de abertura",                 6_000,  2_500, "Você tem agência própria. Só a mídia paga é custo"),
]
print(f"  {'Item':<38}{'Eu pus':>10}{'Realista':>11}   Por quê")
print("  "+"-"*94)
for n,a,d,por in antes:
    print(f"  {n:<38}{brl(a):>10}{brl(d):>11}   {por}")
ta, td = sum(x[1] for x in antes), sum(x[2] for x in antes)
print("  "+"-"*94)
print(f"  {'SUBTOTAL — dinheiro que sai e não volta':<38}{brl(ta):>10}{brl(td):>11}")
print(f"""
  + Capital de giro ..................... R$ 28.000  ->  R$ 22.000
    Isso NÃO é gasto. É caixa que fica na conta para pagar folha e reposição até
    o dinheiro das vendas girar. Volta para você. Eu errei em somar isso no
    investimento e calcular payback em cima — inflou o payback artificialmente.

  INVESTIMENTO REAL (o que some) ......... {brl(td)}
  CAIXA DE GIRO (o que fica e volta) ..... R$ 22.000
  TOTAL A TER DISPONÍVEL ................. {brl(td+22_000)}   (eu tinha dito R$ 86.000)""")

print("\n"+"="*98)
print("PARTE 4 · MUDAR A MARCA — A CONTA MÍNIMA E A CONTA CHEIA")
print("="*98)
plot = [
 ("Embalagem personalizada (copo, tampa, colher, sacola)", 7_000, 7_000, "número seu"),
 ("Adesivagem de balcão, freezers e vitrine",              2_500, 2_500, "trocar o adesivo da Degusta pelo seu"),
 ("Uniformes (12 a 15 camisetas)",                         1_200, 1_200, "precisa em qualquer cenário, mas com sua arte"),
 ("Registro no INPI (1 classe, ME/EPP)",                     880, 1_500, "taxa oficial R$ 440-880 + assessoria opcional"),
 ("Cardápio e menu board",                                   800, 1_500, "precisa em qualquer cenário"),
 ("Identidade visual (logo, manual, aplicações)",              0, 5_000, "VOCÊ TEM AGÊNCIA. Custo de fora seria R$ 5 mil"),
 ("Letreiro / fachada",                                        0, 4_000, "NÃO É EXTRA: hoje não tem letreiro nenhum, precisa nos dois caminhos"),
]
print(f"  {'Item':<52}{'Mínimo':>9}{'Cheio':>9}   Observação")
print("  "+"-"*94)
for n,mi,ch,ob in plot:
    print(f"  {n:<52}{brl(mi):>9}{brl(ch):>9}   {ob}")
mi,ch = sum(x[1] for x in plot), sum(x[2] for x in plot)
print("  "+"-"*94)
print(f"  {'TOTAL':<52}{brl(mi):>9}{brl(ch):>9}")
GANHO = 28_565
print(f"""
  Custo mínimo (fazendo a arte na S7, sem letreiro extra) .... {brl(mi)}
  Custo cheio (contratando tudo de fora) ..................... {brl(ch)}
  Ganho anual estimado da marca própria ...................... {brl(GANHO)}

  Payback no cenário mínimo .... {mi/GANHO*12:.1f} meses
  Payback no cenário cheio ..... {ch/GANHO*12:.1f} meses

  Nos dois casos: menos de uma temporada.""")
