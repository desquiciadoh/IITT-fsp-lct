"""Word lists for local PII redaction (AI-R1).

Lower-case data only. redact.py uses it to tell a person's name from a role, a section header,
a city or a company form, and a Telegram handle from a code annotation.
"""
from __future__ import annotations

# Common first names (RU/CIS) in Cyrillic. Used to spot a name anywhere in the text,
# including inflected forms ("Сергею", "Анной").
FIRST_NAMES_CYR = frozenset("""
александр алексей анатолий андрей антон аркадий арсений артём артем артур богдан борис вадим
валентин валерий василий виктор виталий владимир владислав влад всеволод вячеслав геннадий
георгий герман глеб григорий давид даниил данила денис дмитрий евгений егор елисей ефим захар
иван игнат игорь илья кирилл константин лев леонид лука макар максим марк матвей мирон михаил
назар никита николай олег павел пётр петр платон прохор родион роман ростислав руслан савелий
святослав семён семен сергей станислав степан тарас тимофей тимур тихон фёдор федор филипп
эдуард эрик юрий яков ярослав демьян рустам ринат айдар азат марат ильдар эльдар камиль наиль
дамир ильнур рамиль альберт мурат аслан рафаэль
александра алёна алена алина алиса алла анастасия ангелина анжелика анна антонина арина
валентина валерия варвара вера вероника виктория галина дарья диана ева евгения екатерина
елена елизавета жанна зинаида зоя злата инна ирина карина кира кристина ксения лариса лидия
лилия любовь людмила маргарита марина мария милана надежда наталья наталия нина оксана олеся
ольга полина раиса регина светлана софия софья таисия тамара татьяна ульяна юлия яна эльвира
алия гульнара лейла динара камила зарина алсу айгуль эмилия василиса снежана стефания элина
эвелина
""".split())

# Latin transliterations and common English first names.
FIRST_NAMES_LAT = frozenset("""
alexander aleksandr alexandr alex alexey alexei aleksei aleksey anatoly andrey andrei anton
arkady arseny artem artyom artur arthur bogdan boris vadim valentin valery vasily vasiliy
victor viktor vitaly vitaliy vladimir vladislav vlad vsevolod vyacheslav gennady georgy gleb
grigory gregory david daniil daniel danila denis dmitry dmitriy dmitrii dmitri evgeny evgeniy
eugene egor yegor zakhar ivan igor ilya ilia kirill konstantin leonid makar maxim maksim
matvey miron mikhail michael nikita nikolay nikolai oleg pavel paul petr pyotr peter platon
roman rostislav ruslan svyatoslav semyon sergey sergei serge stanislav stepan taras timofey
timur fedor fyodor philipp filipp eduard eric erik yury yuri iurii yaroslav rustam rinat aidar
azat marat ildar eldar kamil damir ilnur ramil albert murat aslan yakov
alexandra alena alyona alina alisa alla anastasia angelina anna antonina arina valentina
valeria varvara vera veronika veronica victoria viktoria galina darya daria diana eva evgenia
ekaterina katerina elena helen elizaveta zhanna zinaida zoya inna irina karina kira kristina
christina ksenia kseniya larisa lidia lilia lyubov lyudmila ludmila margarita marina maria
mariya milana nadezhda natalia natalya natalie nina oksana olesya olga polina raisa regina
svetlana sofia sofya sophia taisia tamara tatiana tatyana ulyana yulia julia iuliia yana
elvira aliya gulnara leila dinara kamila zarina alsu aigul emilia vasilisa elina evelina
anastasiia evgenii evgeniia mariia kseniia aleksandra arsenii timofei matvei vasilii valerii
valeriia gennadii georgii grigorii anatolii vitalii lidiia sofiia taisiia dariia viktoriia
iakov iana olesia liubov liudmila yuliya ulyana
john james robert william richard thomas mary sarah emma emily kate jessica jennifer
john james robert william richard thomas charles christopher matthew anthony steven andrew
joshua kevin brian jessica sarah emily emma olivia linda susan mary jennifer elizabeth
barbara nancy lisa kate
""".split())

# Endings of inflected first names: "Иван" -> "Ивана", "Сергей" -> "Сергею", "Анна" -> "Анной".
FIRST_NAME_ENDINGS = frozenset({
    "", "а", "я", "у", "ю", "е", "ы", "и", "ом", "ем", "ём", "ой", "ей", "ою", "ею",
})

# A token ending like this is a patronymic, also inflected ("Ивановичем", "Сергеевной").
# "Иванович", "Ивановичем", "Ильич", "Ивановна", "Ильиничной"; not "основные", "личный"
PATRONYMIC_RE = r"(?:(?:ович|евич|ьич)(?:а|у|ем|е)?|(?:овн|евн|ичн)(?:а|ы|е|у|ой|ою))"

# Typical surname endings (scored, never decisive on their own for Latin text).
SURNAME_SUFFIXES_CYR = (
    "ов", "ев", "ёв", "ин", "ын", "ский", "цкий", "ской", "ова", "ева", "ёва", "ина", "ына",
    "ская", "цкая", "енко", "ук", "юк", "чук", "ян", "дзе", "швили", "их", "ых",
)
SURNAME_SUFFIXES_LAT = (
    "ov", "ova", "ev", "eva", "in", "ina", "sky", "skiy", "skaya", "enko", "uk", "yuk", "chuk",
    "yan", "dze", "shvili",
)

# Words that are never part of a name: roles, section headers, cities, company forms.
ROLE_WORDS = frozenset("""
developer engineer programmer разработчик разработчица программист инженер lead senior middle
junior intern стажер стажёр тимлид архитектор architect devops qa tester тестировщик frontend
backend fullstack full-stack scientist analyst аналитик manager менеджер product project owner
designer дизайнер director директор руководитель head chief cto ceo cio cpo team специалист
specialist consultant консультант administrator администратор researcher исследователь
ведущий старший младший главный principal staff data ml ai mlops sre support mobile ios
android web веб game engineering software hardware security cloud platform
""".split())

SECTION_WORDS = frozenset("""
основные компетенции обязанности требования условия задачи ключевые
опыт работы работа навыки образование контакты контакт обо мне себе желаемая должность зарплата
зарплатные ожидания город телефон почта резюме профиль портфолио гражданство пол мужчина
женщина возраст языки английский русский курсы сертификаты проекты достижения хобби интересы
увлечения дополнительная информация ключевые личные качества рекомендации специализация
занятость график полная удаленная удалённая офис гибрид стек технологии summary experience
education skills contacts contact profile projects about languages certificates courses
objective curriculum vitae resume personal information key
""".split())

CITY_WORDS = frozenset("""
москва санкт-петербург петербург спб новосибирск екатеринбург казань нижний новгород самара
краснодар сочи ростов-на-дону минск россия беларусь казахстан алматы астана воронеж пермь уфа
челябинск омск тюмень томск иркутск владивосток красноярск волгоград саратов ярославль тула
калининград moscow russia saint petersburg kazan novosibirsk minsk
""".split())

COMPANY_WORDS = frozenset("""
ооо оао зао пао ао ип нко llc inc ltd corp gmbh компания company банк bank холдинг group
группа студия studio агентство agency лаборатория labs lab университет university институт
institute академия academy колледж college школа school факультет faculty кафедра
государственный технический федеральный национальный исследовательский state technical
national federal
яндекс yandex сбер сбербанк sber тинькофф tinkoff т-банк озон ozon авито avito вк vk bosch
siemens samsung huawei microsoft google amazon apple oracle ibm intel nvidia
команда команды команде команду система системы системный системная великого великий
""".split())

# Decorators and annotations that look like "@handle" but are code (AI-R1 item 2).
CODE_ANNOTATIONS = frozenset("""
dataclass dataclasses pytest fixture mark parametrize property staticmethod classmethod
abstractmethod cached_property lru_cache cache wraps contextmanager asynccontextmanager
overload override final total_ordering singledispatch validator field_validator
model_validator root_validator receiver shared_task task api_view action login_required
csrf_exempt atomic app router route get post put patch delete test describe before after
beforeeach aftereach beforeall afterall mock autowired component service repository
controller restcontroller configuration bean entity table column id generatedvalue onetomany
manytoone manytomany onetoone joincolumn transactional requestmapping getmapping postmapping
putmapping deletemapping patchmapping pathvariable requestparam requestbody responsebody
springbootapplication enableautoconfiguration value data builder getter setter slf4j
noargsconstructor allargsconstructor requiredargsconstructor tostring equalsandhashcode
deprecated functionalinterface suppresswarnings nonnull nullable notnull valid inject
injectable ngmodule input output viewchild hostlistener pipe directive composable preview
jsonproperty jsonignore media import keyframes supports mixin include extend use apply layer
tailwind param return returns throws see since author version todo type typedef example
interface emits props click submit
""".split())

# Tokens shaped like domains that are technologies, not personal sites.
TECH_DOMAIN_TOKENS = frozenset({
    "asp.net", "ado.net", "vb.net", "ml.net", "socket.io", "node.js", "vue.js", "next.js",
    "nuxt.js", "react.js", "express.js", "nest.js", "three.js", "chart.js", "d3.js",
    # tools and employers written as domains
    "draw.io", "fast.ai", "h2o.ai", "neptune.ai", "sentry.io", "akka.net", "quartz.net",
    "mail.ru", "auto.ru", "kaspi.kz", "booking.com", "cloud.ru", "ozon.ru", "avito.ru", "hh.ru",
    "sber.ru", "vk.com", "ivi.ru", "kinopoisk.ru", "lamoda.ru", "wildberries.ru", "2gis.ru",
})

# Values after a profile label that are achievements, not handles ("Kaggle: Expert", "VK — Senior")
PROFILE_NON_HANDLES = frozenset("""
expert master grandmaster contributor novice senior middle junior lead team developer engineer
""".split())
