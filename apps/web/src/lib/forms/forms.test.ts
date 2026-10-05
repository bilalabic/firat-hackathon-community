import { describe, expect, it } from "vitest";

import { checkBotGuards } from "./guard";
import {
  COMMUNITY_CONSENT_VERSION,
  normalizePhone,
  normalizeTelegramUsername,
  parseCommunityForm,
  parseTeamForm,
  TEAM_CONSENT_VERSION,
} from "./schemas";

function formData(entries: Record<string, string | string[]>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(entries)) {
    for (const item of Array.isArray(value) ? value : [value]) data.append(key, item);
  }
  return data;
}

describe("normalizePhone", () => {
  it.each([
    ["0532 123 45 67", "+905321234567"],
    ["532 123 45 67", "+905321234567"],
    ["(0532) 123-45-67", "+905321234567"],
    ["905321234567", "+905321234567"],
    ["+90 532 123 45 67", "+905321234567"],
    ["0090 532 123 45 67", "+905321234567"],
    ["+49 151 23456789", "+4915123456789"],
  ])("normalizes %s", (input, expected) => {
    expect(normalizePhone(input)).toBe(expected);
  });

  it.each(["", "12345", "0212 123 45 67", "+90 212 123 45 67", "+0123456789", "abc"])(
    "rejects %s",
    (input) => {
      expect(normalizePhone(input)).toBeNull();
    },
  );
});

describe("normalizeTelegramUsername", () => {
  it("strips a leading @", () => expect(normalizeTelegramUsername(" @ali_veli ")).toBe("ali_veli"));
  it("rejects short or invalid names", () => {
    expect(normalizeTelegramUsername("abc")).toBeNull();
    expect(normalizeTelegramUsername("ali-veli")).toBeNull();
  });
});

describe("parseCommunityForm", () => {
  const base = {
    full_name: "  Ayşe Yılmaz ",
    university: "Fırat Üniversitesi",
    year_of_study: "2",
    interests: ["ai", "web", "ai"],
    experience_level: "",
    preferred_channel: "whatsapp",
    phone: "0532 123 45 67",
    telegram_username: "ignored_name",
    consent: "on",
  };

  it("builds the payload with only the chosen channel's contact", () => {
    const result = parseCommunityForm(formData(base));
    expect(result).toEqual({
      success: true,
      payload: {
        full_name: "Ayşe Yılmaz",
        university: "Fırat Üniversitesi",
        field_of_study: undefined,
        year_of_study: "2",
        interests: ["ai", "web"],
        experience_level: undefined,
        looking_for: undefined,
        preferred_channel: "whatsapp",
        phone: "+905321234567",
        message: undefined,
        consent_version: COMMUNITY_CONSENT_VERSION,
      },
    });
  });

  it("asks for a Telegram username only for Telegram", () => {
    const result = parseCommunityForm(
      formData({ ...base, preferred_channel: "telegram", telegram_username: "@ayse_y" }),
    );
    expect(result.success && result.payload).toMatchObject({ telegram_username: "ayse_y" });
    expect(result.success && "phone" in result.payload).toBe(false);
  });

  it("reports every invalid field at once", () => {
    const result = parseCommunityForm(
      formData({ ...base, full_name: "A", phone: "123", consent: "", year_of_study: "9" }),
    );
    expect(result.success).toBe(false);
    if (result.success) return;
    expect(Object.keys(result.fieldErrors).sort()).toEqual(
      ["consent", "full_name", "phone", "year_of_study"].sort(),
    );
  });

  it("requires a channel", () => {
    const result = parseCommunityForm(formData({ ...base, preferred_channel: "" }));
    expect(!result.success && result.fieldErrors.preferred_channel).toBeTruthy();
  });

  it("enforces the DB length limits", () => {
    const result = parseCommunityForm(formData({ ...base, message: "x".repeat(1001) }));
    expect(!result.success && result.fieldErrors.message).toBeTruthy();
  });

  it("rejects unknown interests", () => {
    const result = parseCommunityForm(formData({ ...base, interests: ["cooking"] }));
    expect(!result.success && result.fieldErrors.interests).toBeTruthy();
  });
});

describe("parseTeamForm", () => {
  const base = {
    full_name: "Mehmet Kaya",
    areas: ["frontend", "design"],
    github_url: "https://github.com/mehmet",
    linkedin_url: "",
    availability: "4-7h",
    consent: "on",
  };

  it("builds the payload", () => {
    const result = parseTeamForm(formData(base));
    expect(result).toEqual({
      success: true,
      payload: {
        full_name: "Mehmet Kaya",
        affiliation: undefined,
        areas: ["frontend", "design"],
        skills: undefined,
        github_url: "https://github.com/mehmet",
        linkedin_url: undefined,
        availability: "4-7h",
        motivation: undefined,
        consent_version: TEAM_CONSENT_VERSION,
      },
    });
  });

  it("requires at least one area and valid profile URLs", () => {
    const result = parseTeamForm(
      formData({
        ...base,
        areas: [],
        github_url: "http://github.com/x",
        linkedin_url: "https://evil.example/linkedin.com/",
      }),
    );
    expect(result.success).toBe(false);
    if (result.success) return;
    expect(Object.keys(result.fieldErrors).sort()).toEqual(["areas", "github_url", "linkedin_url"]);
  });

  it("accepts a country-prefixed LinkedIn URL", () => {
    const result = parseTeamForm(formData({ ...base, linkedin_url: "https://tr.linkedin.com/in/x" }));
    expect(result.success).toBe(true);
  });
});

describe("checkBotGuards", () => {
  it("flags a filled honeypot", () => {
    expect(checkBotGuards(formData({ website: "http://spam", elapsed_ms: "9000" }))).toBe("honeypot");
  });
  it("flags submissions faster than 3 s or without timing", () => {
    expect(checkBotGuards(formData({ elapsed_ms: "2999" }))).toBe("too_fast");
    expect(checkBotGuards(formData({}))).toBe("too_fast");
    expect(checkBotGuards(formData({ elapsed_ms: "abc" }))).toBe("too_fast");
  });
  it("accepts a normal submission", () => {
    expect(checkBotGuards(formData({ website: "", elapsed_ms: "3000" }))).toBe("ok");
  });
});
