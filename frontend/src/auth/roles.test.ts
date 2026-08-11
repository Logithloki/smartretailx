import { describe, expect, it } from "vitest";
import { isAdminProfile } from "./roles";

describe("isAdminProfile", () => {
  it("does not infer administrator access from an email address", () => {
    expect(
      isAdminProfile({ email: "admin@example.com", "cognito:groups": ["customer"] }),
    ).toBe(false);
  });

  it("recognises only the authoritative admin Cognito group", () => {
    expect(isAdminProfile({ "cognito:groups": ["admin"] })).toBe(true);
    expect(isAdminProfile({ "cognito:groups": ["admins"] })).toBe(false);
    expect(isAdminProfile({ "cognito:groups": "admin" })).toBe(false);
  });
});
