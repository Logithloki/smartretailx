import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  fetchUserAttributes,
  updateUserAttributes,
  confirmUserAttribute,
} from "aws-amplify/auth";
import {
  loadProfileAttributes,
  saveProfileAttributes,
  verifyEmailAttribute,
} from "./profile-service";

vi.mock("aws-amplify/auth", () => ({
  fetchUserAttributes: vi.fn(),
  updateUserAttributes: vi.fn(),
  confirmUserAttribute: vi.fn(),
}));

describe("profile-service", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  describe("loadProfileAttributes", () => {
    it("returns mapped attributes from fetchUserAttributes", async () => {
      vi.mocked(fetchUserAttributes).mockResolvedValueOnce({
        email: "test@example.com",
        given_name: "John",
        family_name: "Doe",
      });

      const result = await loadProfileAttributes();
      expect(result).toEqual({
        email: "test@example.com",
        given_name: "John",
        family_name: "Doe",
      });
    });

    it("returns empty strings for missing attributes", async () => {
      vi.mocked(fetchUserAttributes).mockResolvedValueOnce({
        email: "test@example.com",
      });

      const result = await loadProfileAttributes();
      expect(result).toEqual({
        email: "test@example.com",
        given_name: "",
        family_name: "",
      });
    });
  });

  describe("saveProfileAttributes", () => {
    it("sends only provided attributes to updateUserAttributes", async () => {
      vi.mocked(updateUserAttributes).mockResolvedValueOnce({
        given_name: { isUpdated: true, nextStep: { updateAttributeStep: "DONE" } },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any);

      const result = await saveProfileAttributes({
        given_name: "Jane",
      });

      expect(updateUserAttributes).toHaveBeenCalledWith({
        userAttributes: {
          given_name: "Jane",
        },
      });
      expect(result.isUpdated).toBe(true);
      expect(result.nextStep).toBeUndefined();
    });

    it("handles email verification step correctly", async () => {
      vi.mocked(updateUserAttributes).mockResolvedValueOnce({
        email: {
          isUpdated: false,
          nextStep: {
            updateAttributeStep: "CONFIRM_ATTRIBUTE_WITH_CODE",
            codeDeliveryDetails: {
              attributeName: "email",
              deliveryMedium: "EMAIL",
              destination: "t***@e***",
            },
          },
        },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any);

      const result = await saveProfileAttributes({
        email: "test@example.com",
      });

      expect(result.isUpdated).toBe(false);
      expect(result.nextStep).toEqual({
        updateAttributeStep: "CONFIRM_ATTRIBUTE_WITH_CODE",
        codeDeliveryDetails: {
          attributeName: "email",
          deliveryMedium: "EMAIL",
          destination: "t***@e***",
        },
      });
    });
  });

  describe("verifyEmailAttribute", () => {
    it("calls confirmUserAttribute with correct arguments", async () => {
      vi.mocked(confirmUserAttribute).mockResolvedValueOnce();

      await verifyEmailAttribute("123456");

      expect(confirmUserAttribute).toHaveBeenCalledWith({
        userAttributeKey: "email",
        confirmationCode: "123456",
      });
    });
  });
});
