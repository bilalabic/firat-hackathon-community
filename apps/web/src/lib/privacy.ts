// KVKK aydınlatma metni: the single source for /aydinlatma-metni and the form summary.
// Approved by the owner on 2026-10-06 (docs/legal/KVKK_AYDINLATMA_METNI.md, D-22).
// Changing the meaning of this text requires a new consent version in lib/forms/schemas.ts.

export const PRIVACY_NOTICE_UPDATED = "6 Ekim 2026";

export const controller = {
  name: "Bilal Abiç",
  role: "Fırat Hackathon Community yöneticisi",
  email: "bilalabic78@gmail.com",
} as const;

export type NoticeBlock =
  | { kind: "p"; text: string }
  | { kind: "list"; items: readonly string[] }
  | { kind: "table"; head: readonly string[]; rows: readonly (readonly string[])[] };

export type NoticeSection = { id: string; title: string; blocks: readonly NoticeBlock[] };

export const privacyNotice = {
  title: "Aydınlatma metni",
  lead:
    "Topluluğa Katıl ve Ekibe Katıl formlarıyla paylaştığın kişisel verilerin nasıl işlendiğini, 6698 sayılı Kişisel Verilerin Korunması Kanunu (KVKK) madde 10 uyarınca burada anlatıyoruz.",
  sections: [
    {
      id: "veri-sorumlusu",
      title: "1. Veri sorumlusu",
      blocks: [
        {
          kind: "p",
          text: `${controller.name} (${controller.role}). İletişim: ${controller.email}`,
        },
      ],
    },
    {
      id: "islenen-veriler",
      title: "2. İşlenen kişisel veriler",
      blocks: [
        { kind: "p", text: "Topluluğa Katıl formunda:" },
        {
          kind: "list",
          items: [
            "Kimlik: ad soyad.",
            "Eğitim: üniversite, bölüm, sınıf.",
            "Kendi verdiğin bilgiler: ilgi alanların, deneyim düzeyin, topluluktan beklentin ve isteğe bağlı mesajın.",
            "İletişim: tercih ettiğin kanal ve yalnızca o kanala ait bilgi. Telegram'ı seçersen Telegram kullanıcı adın, WhatsApp'ı seçersen cep telefonu numaran.",
          ],
        },
        { kind: "p", text: "Ekibe Katıl formunda:" },
        {
          kind: "list",
          items: [
            "Kimlik: ad soyad.",
            "Kurum veya üniversite.",
            "Kendi verdiğin bilgiler: ilgilendiğin çalışma alanları, yeteneklerin, haftalık uygunluğun ve motivasyonun.",
            "Bağlantılar: isteğe bağlı GitHub ve LinkedIn profil adresin.",
          ],
        },
        {
          kind: "p",
          text: "Her iki formda bu metni onayladığın tarih ve metnin sürümü kaydedilir. IP adresin, tarayıcı bilgin veya konumun kaydedilmez. Otomatik gönderimleri ayırt etmek için formun açık kaldığı süre ölçülür; bu süre saklanmaz.",
        },
      ],
    },
    {
      id: "amaclar",
      title: "3. İşleme amaçları",
      blocks: [
        {
          kind: "list",
          items: [
            "Topluluğa katılım başvurunu değerlendirmek ve seçtiğin kanal üzerinden (Telegram veya WhatsApp) seninle iletişime geçmek.",
            "Ekip başvurunu değerlendirmek ve sana dönüş yapmak.",
            "Başvurunun durumunu takip etmek (yeni, iletişime geçildi, kabul, ret).",
            "Kötüye kullanımı ve spam başvuruları önlemek.",
          ],
        },
        {
          kind: "p",
          text: "Verilerin pazarlama, reklam veya profil çıkarma amacıyla kullanılmaz ve satılmaz.",
        },
      ],
    },
    {
      id: "hukuki-sebep",
      title: "4. Toplama yöntemi ve hukuki sebep",
      blocks: [
        {
          kind: "p",
          text: "Verilerin bu sitedeki formlar aracılığıyla, doğrudan senin tarafından ve elektronik ortamda toplanır. Hukuki sebep, KVKK madde 5/1 uyarınca açık rızandır: formu göndermeden önce bu metni okuduğunu ve verilerinin işlenmesine ve aşağıda açıklanan yurt dışı aktarıma açık rıza verdiğini işaretlersin. Bu onay verilmeden başvuru gönderilemez.",
        },
      ],
    },
    {
      id: "aktarim",
      title: "5. Aktarım ve kullanılan hizmet sağlayıcılar",
      blocks: [
        {
          kind: "p",
          text: "Başvurularının içeriğini yalnızca veri sorumlusu görür ve bu içerik üçüncü kişilerle paylaşılmaz. Hizmetin çalışması için şu sağlayıcılar kullanılır:",
        },
        {
          kind: "table",
          head: ["Sağlayıcı", "Ne için", "Verinin bulunduğu yer"],
          rows: [
            ["Supabase", "Başvuruların saklandığı veritabanı", "Avrupa Birliği (Frankfurt, Almanya)"],
            [
              "Vercel",
              "Sitenin ve formların çalıştığı altyapı",
              "Form işlemleri Frankfurt bölgesinde çalışır; şirket ABD merkezlidir",
            ],
            [
              "Telegram",
              "Veri sorumlusuna yeni başvuru bildirimi",
              "Bildirimde yalnızca adın, başvuru türü ve seçtiğin kanal yer alır; telefon numaran, kullanıcı adın ve mesajın gönderilmez",
            ],
          ],
        },
      ],
    },
    {
      id: "yurt-disi",
      title: "6. Yurt dışına aktarım",
      blocks: [
        {
          kind: "p",
          text: "Yukarıdaki sağlayıcıların sunucuları Türkiye dışında olduğundan verilerin yurt dışına aktarılır. Bu aktarım, formda ayrıca onayladığın açık rızana dayanır (KVKK madde 9). Rıza vermek istemezsen başvuru formunu kullanmadan, aşağıdaki e-posta adresi üzerinden de bizimle iletişime geçebilirsin.",
        },
      ],
    },
    {
      id: "saklama",
      title: "7. Saklama süresi",
      blocks: [
        {
          kind: "p",
          text: "Başvuru verilerin, başvurunun son işlem tarihinden itibaren 12 ay saklanır; bu sürenin sonunda silinir veya anonim hale getirilir. Silinmesini istersen daha erken silinir.",
        },
      ],
    },
    {
      id: "haklar",
      title: "8. Hakların",
      blocks: [
        { kind: "p", text: "KVKK madde 11 uyarınca veri sorumlusuna başvurarak şunları talep edebilirsin:" },
        {
          kind: "list",
          items: [
            "Kişisel verilerinin işlenip işlenmediğini öğrenmek ve işlenmişse bilgi istemek.",
            "İşlenme amacını ve amacına uygun kullanılıp kullanılmadığını öğrenmek.",
            "Yurt içinde veya yurt dışında aktarıldığı üçüncü kişileri bilmek.",
            "Eksik veya yanlış işlenmişse düzeltilmesini istemek.",
            "KVKK madde 7'deki şartlar çerçevesinde silinmesini veya yok edilmesini istemek.",
            "Düzeltme ve silme işlemlerinin aktarıldığı üçüncü kişilere bildirilmesini istemek.",
            "Münhasıran otomatik sistemlerle analiz edilmesi sonucu aleyhine bir sonuç çıkmasına itiraz etmek.",
            "Kanuna aykırı işleme nedeniyle zarara uğrarsan zararın giderilmesini istemek.",
          ],
        },
        {
          kind: "p",
          text: `Açık rızanı istediğin zaman geri alabilirsin; bu, geri alma tarihine kadar yapılan işlemleri etkilemez. Talebini ${controller.email} adresine e-posta ile iletebilirsin; talebin en geç 30 gün içinde ücretsiz olarak sonuçlandırılır.`,
        },
      ],
    },
  ],
  formSummary:
    "Bilgilerin yalnızca başvurunu değerlendirmek ve seninle iletişime geçmek için kullanılır, 12 ay saklanır ve Supabase (Frankfurt), Vercel ve Telegram (yalnızca adın) gibi yurt dışındaki hizmet sağlayıcılarda işlenir.",
  formLinkLabel: "Aydınlatma metninin tamamını oku",
} as const satisfies {
  title: string;
  lead: string;
  sections: readonly NoticeSection[];
  formSummary: string;
  formLinkLabel: string;
};
