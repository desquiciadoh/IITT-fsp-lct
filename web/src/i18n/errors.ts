/** Russian messages per backend error code (FE1.md FE-02). */

export const ERROR_MESSAGES: Record<string, string> = {
  validation_failed: 'Проверьте правильность заполнения полей.',
  email_taken: 'Пользователь с таким email уже зарегистрирован.',
  bad_credentials: 'Неверный email или пароль.',
  unauthorized: 'Сессия истекла, войдите снова.',
  email_unverified: 'Email не подтверждён. Проверьте почту.',
  token_invalid: 'Ссылка недействительна или устарела.',
  rate_limited: 'Слишком много попыток. Попробуйте позже.',
  forbidden: 'Недостаточно прав для этого действия.',
  not_found: 'Запись не найдена.',
  fsp_id_already_linked: 'FSP ID уже привязан к другому аккаунту.',
  cooldown_active: 'Пересдача пока недоступна — действует пауза.',
  assessment_in_progress: 'Тест уже начат. Завершите текущую попытку.',
  item_not_current: 'Ответ принят не на текущий вопрос — обновление…',
  assessment_expired: 'Время теста истекло.',
  not_finished: 'Тест ещё не завершён.',
  not_enough_answers: 'Отвечено меньше половины заданий — попытка засчитана как прерванная.',
  fallback_not_available: 'Фолбэк сейчас недоступен.',
  unreadable_pdf: 'Не удалось прочитать PDF. Заполните форму вручную.',
  salary_invalid: 'Проверьте диапазон зарплаты.',
  candidate_not_reachable: 'Кандидат недоступен: профиль скрыт или не виден вашей компании.',
  invalid_transition: 'Это действие сейчас недоступно для статуса оффера.',
  version_conflict: 'Данные изменились — страница будет обновлена.',
  contact_not_granted: 'Контакты пока не раскрыты.',
  no_credits: 'Лимит отправок на неделю исчерпан.',
  company_required: 'Сначала создайте профиль компании.',
  api_error: 'Что-то пошло не так. Попробуйте ещё раз.',
}

export function errorMessage(code: string | undefined, fallback?: string): string {
  if (code && ERROR_MESSAGES[code]) return ERROR_MESSAGES[code]
  return fallback ?? ERROR_MESSAGES.api_error
}
