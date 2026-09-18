// Explicações curtas, em linguagem simples, dos termos técnicos da ficha.
// Usadas como tooltip (hover) no componente <Term/>.
export const GLOSSARY: Record<string, string> = {
  'Projeção térreo':
    'Área máxima que a construção pode ocupar no térreo = Taxa de Ocupação × área do lote.',
  TO: 'Taxa de Ocupação: quanto do lote (%) a edificação pode cobrir no térreo.',
  'Permeável mín':
    'Área do lote que deve ficar sem pavimentar, para absorver a chuva (Taxa de Área Permeável).',
  TAP: 'Taxa de Área Permeável: % mínimo do lote que deve permanecer permeável (sem piso/laje).',
  Recuo: 'Distância mínima obrigatória entre a construção e os limites do lote (frente, lados, fundo).',
  Zona: 'Classificação da LUOS que define o que e quanto se pode construir no lote.',
  Altura:
    'Em João Pessoa a altura é espacial: "livre" (limitada só pelos recuos), escalonada na faixa de 500 m da orla, ou restrita (centro histórico).',
  IPHAEP:
    'Instituto do Patrimônio Histórico do estado — impõe restrição de altura e de intervenção no lote.',
  'Faixa orla':
    'Faixa de 500 m a partir da praia onde a altura é escalonada: quanto mais perto do mar, mais baixo.',
  Usos: 'Atividades permitidas (residencial, comércio, serviço…), conforme a hierarquia da via (Anexo IV).',
  'R$/m² terreno': 'Preço pedido no anúncio dividido pela área do lote.',
  VGV: 'Valor Geral de Vendas: receita potencial total das unidades = área privativa × R$/m² de venda.',
  'Valor residual':
    'Quanto vale pagar pelo terreno: o que sobra do VGV depois de obra, impostos, comercialização, indiretos e a margem-alvo do incorporador (método involutivo).',
  IncorpoScore:
    'Nota 0–100 de atratividade do lote, de 4 eixos: rentabilidade, aproveitamento, localização e confiança. Relativa às premissas e preliminar — ordena oportunidades, não substitui análise.',
}
