// Every public UI string lives here (D-18). Event content itself stays in its original language.
// Keep this module free of server-only imports: client components read it too.

import type { EventFormat, TabSlug } from "./routes";

export const site = {
  name: "Fırat Hackathon Community",
  shortName: "Fırat Hackathon",
  tagline: "Hackathonları keşfet, ekibini bul, katıl.",
  description:
    "Fırat Hackathon Community tarafından takip edilen hackathon ve teknoloji yarışmaları. Başvurusu açık etkinlikleri ve son tarihleri gör, ekibini bul, katıl.",
  ogImageAlt: "Hackathon etkinlik kartı",
} as const;

export const nav = {
  label: "Ana menü",
  skipToContent: "İçeriğe geç",
  home: "Ana sayfa",
  events: "Hackathonlar",
  community: "Topluluk",
  contribute: "Katkı",
  about: "Hakkında",
} as const;

export const footer = {
  line: "Gönüllüler tarafından yürütülen açık kaynak bir topluluk projesi.",
  github: "GitHub",
  sources:
    "Etkinlik bilgileri resmî kaynaklardan derlenir. Başvurmadan önce resmî sayfayı kontrol et.",
} as const;

export const common = {
  opensInNewTab: "(yeni sekmede açılır)",
  datesTba: "Tarih açıklanacak",
  notSpecified: "Belirtilmedi",
  allEvents: "Tüm hackathonlar",
  seeAll: "Tümünü gör",
} as const;

export const phaseLabels = {
  open: "Başvurular açık",
  upcoming: "Yaklaşan",
  past: "Sona erdi",
} as const;

/** Countdown to the application deadline. */
export function deadlineCountdown(daysLeft: number): string {
  if (daysLeft <= 0) return "Bugün son gün";
  if (daysLeft === 1) return "Yarın son gün";
  return `${daysLeft} gün kaldı`;
}

export const formatLabels: Record<EventFormat, string> = {
  in_person: "Yüz yüze",
  online: "Çevrim içi",
  hybrid: "Hibrit",
};

export const tabLabels: Record<TabSlug, string> = {
  yaklasan: "Yaklaşan",
  acik: "Başvurular Açık",
  "son-gunler": "Son Günler",
  gecmis: "Geçmiş",
};

export const eventRow = {
  deadline: "Son başvuru",
  eventDate: "Etkinlik",
  online: "Çevrim içi",
} as const;

export const home = {
  title: "Hackathonları kaçırma.",
  lead: "Türkiye'deki ve çevrim içi hackathonları tek listede topluyoruz. Son başvuru tarihini gör, resmî sayfaya git, ekibini toplulukta bul.",
  summary(open: number, closingSoon: number, upcoming: number): string {
    if (open > 0) {
      const soon = closingSoon > 0 ? `, ${closingSoon} tanesinde son günler` : "";
      return `Şu anda ${open} hackathonun başvurusu açık${soon}.`;
    }
    if (upcoming > 0) {
      return `Şu anda başvurusu açık hackathon yok. Takvimde ${upcoming} yaklaşan etkinlik var.`;
    }
    return "Şu anda başvurusu açık hackathon yok. Yeni etkinlikler eklendikçe burada görünecek.";
  },
  closingSoonTitle: "Son günler",
  closingSoonLead: "Başvurusu 7 gün içinde kapanacak hackathonlar.",
  openTitle: "Başvurular açık",
  openLead: "Son başvuru tarihi henüz geçmemiş hackathonlar.",
  upcomingTitle: "Yaklaşan",
  upcomingLead: "Başvurusu açık olmayan, henüz bitmemiş etkinlikler.",
  communityTitle: "Tek başına başvurmak zorunda değilsin",
  communityLead:
    "Topluluğa katıl; etkinlik duyurularını al, takım arkadaşı bul, deneyimlerini paylaş.",
  communityCta: "Topluluğa katıl",
  suggestTitle: "Listede olmayan bir hackathon mu var?",
  suggestLead: "Topluluk üzerinden bize ilet, doğrulayıp ekleyelim.",
  suggestCta: "Etkinlik öner",
} as const;

export const list = {
  title: "Hackathonlar",
  lead: "Başvurusu açık, yaklaşan ve geçmiş hackathonlar. Tarihler etkinliğin saat dilimine göre hesaplanır.",
  tabsLabel: "Etkinlik durumu",
  filtersLabel: "Arama ve filtreler",
  searchLabel: "Ara",
  searchPlaceholder: "Etkinlik, düzenleyici veya şehir",
  formatLabel: "Biçim",
  formatAll: "Tüm biçimler",
  cityLabel: "Şehir",
  cityAll: "Tüm şehirler",
  submit: "Filtrele",
  clear: "Filtreleri temizle",
  loading: "Etkinlikler yükleniyor…",
  resultCount(count: number): string {
    return count === 0 ? "Sonuç yok" : `${count} etkinlik`;
  },
  emptyFiltered: "Aramanla eşleşen etkinlik bulunamadı. Filtreleri temizleyip tekrar dene.",
  emptyTab: {
    yaklasan: "Takvimde yaklaşan etkinlik yok.",
    acik: "Şu anda başvurusu açık hackathon yok. Yaklaşan etkinliklere göz atabilirsin.",
    "son-gunler": "Önümüzdeki 7 gün içinde başvurusu kapanan hackathon yok.",
    gecmis: "Henüz geçmiş etkinlik yok.",
  } satisfies Record<TabSlug, string>,
} as const;

export const detail = {
  back: "Tüm hackathonlar",
  factsLabel: "Etkinlik bilgileri",
  deadline: "Son başvuru",
  deadlinePassed: "Başvurular kapandı",
  dates: "Tarih",
  format: "Biçim",
  location: "Konum",
  team: "Takım",
  teamSize(min: number | null, max: number | null): string {
    if (min !== null && max !== null) {
      return min === max ? `${min} kişi` : `${min}–${max} kişi`;
    }
    if (min !== null) return `En az ${min} kişi`;
    if (max !== null) return `En fazla ${max} kişi`;
    return common.notSpecified;
  },
  eligibility: "Katılım koşulları",
  prize: "Ödül havuzu",
  fee: "Katılım ücreti",
  free: "Ücretsiz",
  paid: "Ücretli",
  organizer: "Düzenleyen",
  about: "Etkinlik hakkında",
  categories: "Kategoriler",
  technologies: "Teknolojiler",
  officialPage: "Resmî sayfa",
  apply: "Başvur",
  lastUpdated: "Son güncelleme",
  unverified:
    "Bu etkinliğin bilgileri henüz resmî kaynakla doğrulanmadı. Başvurmadan önce resmî sayfayı kontrol et.",
  posterAlt(title: string): string {
    return `${title} afişi`;
  },
} as const;

export const notFoundPage = {
  title: "Sayfa bulunamadı",
  lead: "Aradığın sayfa taşınmış, yayından kaldırılmış ya da hiç var olmamış olabilir.",
  cta: "Hackathonlara göz at",
  home: "Ana sayfaya dön",
} as const;

export const errorPage = {
  title: "Bir şeyler ters gitti",
  lead: "Sayfa şu anda yüklenemedi. Biraz sonra tekrar dene.",
  retry: "Tekrar dene",
} as const;

export const community = {
  title: "Topluluk",
  lead: "Fırat Hackathon Community; hackathonlara birlikte hazırlanan, takım kuran ve deneyim paylaşan öğrencilerin topluluğudur.",
  whyTitle: "Neden katılmalısın?",
  why: [
    "Yeni hackathonları ve yaklaşan son başvuru tarihlerini zamanında öğren.",
    "Becerilerini tamamlayan takım arkadaşları bul.",
    "Daha önce katılanların deneyimlerinden ve hazırlık önerilerinden yararlan.",
  ],
  channelsTitle: "Telegram ve WhatsApp",
  channels:
    "Duyurular Telegram ve WhatsApp üzerinden paylaşılır. Formu doldurup tercih ettiğin kanalı seç; davet bağlantısını ekip sana ayrıca gönderir.",
  formTitle: "Topluluğa katıl",
  formLead: "Birkaç soruyu yanıtla, sana uygun kanaldan davet gönderelim.",
} as const;

export const contribute = {
  title: "Katkı",
  lead: "Projeye dört farklı şekilde destek olabilirsin. Sana uygun olanı seç.",
  team: {
    title: "Ekibe katıl",
    lead: "Etkinlikleri araştırmak, siteyi geliştirmek veya topluluğu büyütmek için düzenli zaman ayırabiliyorsan başvur.",
  },
  code: {
    title: "Koda katkı ver",
    lead: "Proje açık kaynak. Kodu incele, hata bildir veya “good first issue” etiketli işlerden biriyle başla.",
    repo: "GitHub deposu",
    issues: "Başlangıç için uygun işler",
  },
  support: {
    title: "Projeyi destekle",
    lead: "Projeyi arkadaşlarınla paylaşmak, GitHub'da yıldız vermek ve katıldığın hackathonları bize bildirmek en büyük destek. Şu an bağış kabul etmiyoruz.",
  },
  suggest: {
    title: "Etkinlik öner",
    lead: "Listede olmayan bir hackathon biliyorsan topluluk kanalından ilet; resmî kaynaktan doğrulayıp ekleyelim.",
    cta: "Topluluk sayfasına git",
  },
} as const;

export const about = {
  title: "Hakkında",
  lead: "Fırat Hackathon Community, hackathon fırsatlarını tek yerde toplayan ve öğrencileri bu etkinliklere birlikte hazırlanmaya davet eden gönüllü bir topluluk projesidir.",
  missionTitle: "Amacımız",
  mission:
    "Hackathon duyuruları sosyal medyada, e-posta listelerinde ve etkinlik platformlarında dağınık hâlde. Biz bu bilgileri resmî kaynaklardan derleyip sade bir takvimde sunuyor, son başvuru tarihlerini kaçırmamanı sağlıyoruz.",
  howTitle: "Nasıl çalışır?",
  how: [
    "Etkinlikler resmî sayfalarından derlenir ve yayına alınmadan önce ekip tarafından gözden geçirilir.",
    "Her etkinlik sayfasında resmî bağlantı bulunur; kesin bilgi için her zaman resmî sayfayı esas al.",
    "Hatalı veya eksik bir bilgi görürsen GitHub üzerinden bildirebilirsin.",
  ],
  whoTitle: "Kim yürütüyor?",
  who: "Proje gönüllüler tarafından yürütülür ve açık kaynaklıdır; kodu ve yol haritası GitHub'da herkese açıktır.",
  contactTitle: "İletişim",
  contact: "Soru, öneri ve düzeltme talepleri için GitHub üzerinden bir issue açabilirsin.",
  contactCta: "GitHub'da issue aç",
} as const;

/** Shared form copy. */
export const form = {
  required: "zorunlu",
  optional: "isteğe bağlı",
  submit: "Başvuruyu gönder",
  submitting: "Gönderiliyor…",
  successTitle: "Başvurun alındı",
  errorSummary: "Form gönderilemedi. İşaretli alanları düzeltip tekrar dene.",
  genericError: "Başvuru şu anda kaydedilemedi. Biraz sonra tekrar dene.",
  tooFast: "Form çok hızlı gönderildi. Alanları kontrol edip tekrar gönder.",
  needsJavaScript:
    "Formu göndermek için tarayıcında JavaScript açık olmalı. JavaScript'i açıp sayfayı yenile.",
  honeypotLabel: "Bu alanı boş bırak",
  consentLabel: "Aydınlatma metnini okudum; bilgilerimin bu başvuru için işlenmesini kabul ediyorum.",
  privacyTitle: "Aydınlatma metni",
  privacyDraftBadge: "TASLAK – yayına alınmadan önce onaylanacak",
  privacyDraft:
    "Kişisel verilerin korunmasına ilişkin aydınlatma metni (KVKK) hazırlanmaktadır. Metin; verilerin hangi amaçla işlendiğini, ne kadar süre saklandığını ve silme talebinin nasıl iletileceğini açıklayacak ve proje sahibi tarafından onaylandıktan sonra burada yayımlanacaktır.",
  errors: {
    fullName: "Ad soyad 2 ile 120 karakter arasında olmalı.",
    tooLong(max: number): string {
      return `En fazla ${max} karakter girebilirsin.`;
    },
    choose: "Listeden bir seçenek seç.",
    channel: "Tercih ettiğin kanalı seç.",
    telegram:
      "Telegram kullanıcı adı 5–32 karakter olmalı; yalnızca harf, rakam ve alt çizgi içerebilir.",
    phone: "Geçerli bir cep telefonu numarası gir (örnek: 0532 123 45 67).",
    interests: "En fazla 10 ilgi alanı seçebilirsin.",
    areas: "En az bir alan seç.",
    github: "Adres https://github.com/ ile başlamalı.",
    linkedin:
      "Adres https:// ile başlayan bir linkedin.com adresi olmalı (örnek: https://www.linkedin.com/in/kullanici-adi).",
    consent: "Devam etmek için aydınlatma metnini onayla.",
  },
} as const;

export const communityForm = {
  success:
    "Teşekkürler! Ekibimiz başvurunu inceleyip seçtiğin kanal üzerinden davet bağlantısını gönderecek.",
  fullName: "Ad soyad",
  university: "Üniversite",
  fieldOfStudy: "Bölüm",
  yearOfStudy: "Sınıf",
  yearPlaceholder: "Seç",
  years: {
    prep: "Hazırlık",
    "1": "1. sınıf",
    "2": "2. sınıf",
    "3": "3. sınıf",
    "4": "4. sınıf",
    "5": "5. sınıf",
    "6": "6. sınıf",
    graduate: "Yüksek lisans / doktora",
    alumni: "Mezun",
    other: "Diğer",
  },
  interests: "İlgi alanların",
  interestsHint: "Birden fazla seçebilirsin.",
  interestOptions: {
    ai: "Yapay zekâ",
    web: "Web geliştirme",
    mobile: "Mobil",
    data: "Veri bilimi",
    security: "Siber güvenlik",
    game: "Oyun geliştirme",
    hardware: "Donanım ve IoT",
    design: "Tasarım",
    entrepreneurship: "Girişimcilik",
    blockchain: "Blokzincir",
  },
  experienceLevel: "Deneyim seviyen",
  experiencePlaceholder: "Seç",
  experienceLevels: {
    none: "Yeni başlıyorum",
    beginner: "Başlangıç",
    intermediate: "Orta",
    advanced: "İleri",
  },
  lookingFor: "Toplulukta ne arıyorsun?",
  lookingForHint: "Örneğin takım arkadaşı, mentor veya etkinlik duyuruları.",
  channel: "Tercih ettiğin kanal",
  channelHint: "İletişim bilgisi yalnızca seçtiğin kanal için istenir.",
  channels: { telegram: "Telegram", whatsapp: "WhatsApp" },
  telegramUsername: "Telegram kullanıcı adı",
  telegramHint: "Başında @ olmadan da yazabilirsin.",
  phone: "Cep telefonu",
  phoneHint: "WhatsApp daveti için kullanılır. Örnek: 0532 123 45 67",
  message: "Eklemek istediğin bir şey var mı?",
} as const;

export const teamForm = {
  success: "Teşekkürler! Başvurunu inceledikten sonra seninle iletişime geçeceğiz.",
  fullName: "Ad soyad",
  affiliation: "Üniversite, bölüm veya kurum",
  areas: "Hangi alanlarda katkı vermek istersin?",
  areasHint: "En az bir alan seç.",
  areaOptions: {
    frontend: "Frontend",
    backend: "Backend",
    ai_automation: "Yapay zekâ ve otomasyon",
    design: "Tasarım",
    content: "İçerik",
    community: "Topluluk yönetimi",
    research: "Etkinlik araştırma",
  },
  skills: "Beceriler",
  skillsHint: "Kullandığın diller, araçlar veya deneyimlerin.",
  githubUrl: "GitHub profili",
  linkedinUrl: "LinkedIn profili",
  availability: "Haftalık ayırabileceğin zaman",
  availabilityPlaceholder: "Seç",
  availabilityOptions: {
    "1-3h": "Haftada 1–3 saat",
    "4-7h": "Haftada 4–7 saat",
    "8h+": "Haftada 8 saat ve üzeri",
  },
  motivation: "Neden ekibe katılmak istiyorsun?",
} as const;
