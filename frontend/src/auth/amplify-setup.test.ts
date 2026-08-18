import { describe, expect, it } from "vitest";
import { __testables } from "./amplify-setup";

describe("extractUserPoolId", () => {
  const { extractUserPoolId } = __testables;

  it("parses a well-formed Cognito issuer URL", () => {
    expect(
      extractUserPoolId("https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_kYIvUeRUp"),
    ).toBe("eu-west-1_kYIvUeRUp");
    expect(
      extractUserPoolId("https://cognito-idp.us-east-1.amazonaws.com/us-east-1_ABC123def"),
    ).toBe("us-east-1_ABC123def");
  });

  it("tolerates a trailing slash", () => {
    expect(
      extractUserPoolId("https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_kYIvUeRUp/"),
    ).toBe("eu-west-1_kYIvUeRUp");
  });

  it("throws for values that are not a Cognito authority", () => {
    for (const bad of [
      "https://example.com/",
      "https://cognito-idp.eu-west-1.amazonaws.com/",
      "https://cognito-idp.eu-west-1.amazonaws.com/not-a-pool",
      "eu-west-1_kYIvUeRUp", // missing scheme+host
    ]) {
      expect(() => extractUserPoolId(bad)).toThrow(/user pool id/);
    }
  });
});
