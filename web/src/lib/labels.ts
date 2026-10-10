/** Russian labels for backend enums. Keys stay English (API contract). */

export const GRADE_LABEL: Record<string, string> = {
  intern: 'стажёр',
  junior: 'джун',
  middle: 'мидл',
  senior: 'синьор',
}

/** Russian descriptors for the grade-claim cards (FE-04). */
export const GRADE_DESCRIPTOR: Record<string, string> = {
  intern:
    'Разбираетесь в базе, решаете задачи с подсказками и наставником. Подходит для первого опыта.',
  junior:
    'Самостоятельно решаете типовые задачи внутри одного сервиса, вопросы задаёте по делу.',
  middle:
    'Владеете направлением: проектируете решения, пишете тесты, отвечаете за результат.',
  senior:
    'Ведёте архитектуру и людей: сложные задачи, код-ревью, разбор инцидентов и найм.',
}

export const SPEC_LABEL: Record<string, string> = {
  backend: 'бэкенд',
  frontend: 'фронтенд',
  ml_data: 'ml/data',
}

export const LEAGUE_STATUS_LABEL: Record<string, string> = {
  pending: 'ожидает',
  confirmed: 'подтверждён',
  unconfirmed: 'неподтверждён',
}

/** Position lifecycle (BE `Position.status`, OpenAPI `positionStatusEnum`). */
export const POSITION_STATUS_LABEL: Record<string, string> = {
  open: 'открыта',
  closed: 'закрыта',
}

export const OFFER_STATUS_LABEL: Record<string, string> = {
  sent: 'отправлен',
  viewed: 'просмотрен',
  accepted: 'принят',
  declined: 'отклонён',
  withdrawn: 'отозван',
  expired: 'истёк',
  interview: 'интервью',
  hired: 'нанят',
  closed: 'закрыт',
}

export const WORK_FORMAT_LABEL: Record<string, string> = {
  office: 'офис',
  hybrid: 'гибрид',
  remote: 'удалённо',
}

export const SALARY_TYPE_LABEL: Record<string, string> = {
  gross: 'до вычета',
  net: 'на руки',
}

export const DECLINE_REASON_LABEL: Record<string, string> = {
  salary: 'зарплата',
  stack: 'стек',
  format: 'формат работы',
  company: 'компания',
  timing: 'тайминг',
  not_looking: 'не ищу работу',
  other: 'другое',
}

export const CONTACT_CHANNEL_LABEL: Record<string, string> = {
  email: 'email',
  phone: 'телефон',
  telegram: 'telegram',
  platform: 'платформа',
}

export const SOURCE_LABEL: Record<string, string> = {
  test: 'подтверждено тестом',
  fsp: 'подтверждено ФСП',
  microtask: 'микрозадача',
  declared: 'заявлено кандидатом',
}

export const SPORTS_RANK_LABEL: Record<string, string> = {
  cat3: '3 кат.',
  cat2: '2 кат.',
  cat1: '1 кат.',
  kms: 'КМС',
  ms: 'МС',
}

export const PLACEMENT_TIER_LABEL: Record<string, string> = {
  winner: 'победитель',
  prize_winner: 'призёр',
  finalist: 'финалист',
  participant: 'участник',
}
