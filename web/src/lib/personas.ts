/** Demo personas shared by the login screen and Jury Mode (FE-03). */

export type PersonaId = 'candidate_fsp' | 'candidate_plain' | 'employer'

export type Persona = {
  id: PersonaId
  shortLabel: string
  title: string
  description: string
}

export const PERSONAS: Persona[] = [
  {
    id: 'candidate_fsp',
    shortLabel: 'Анна (ФСП)',
    title: 'Анна — чемпион ФСП',
    description: 'Senior-бэкенд, подтверждённые спортивные результаты ФСП.',
  },
  {
    id: 'candidate_plain',
    shortLabel: 'Алекс',
    title: 'Алекс — без ФСП',
    description: 'Middle-разработчик, спортивных результатов нет.',
  },
  {
    id: 'employer',
    shortLabel: 'Работодатель',
    title: 'Yandex Tech',
    description: 'Компания: пул талантов, вакансии и отправка офферов.',
  },
]
