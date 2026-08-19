import { describe, it, expect, vi } from "vitest";
import { updatePassword } from "aws-amplify/auth";
import { changePassword } from "./password-service";

vi.mock("aws-amplify/auth", () => ({
  updatePassword: vi.fn(),
}));

describe("password-service", () => {
  it("calls updatePassword with the old and new passwords", async () => {
    vi.mocked(updatePassword).mockResolvedValueOnce();

    await changePassword("oldPass123!", "newPass456!");

    expect(updatePassword).toHaveBeenCalledWith({
      oldPassword: "oldPass123!",
      newPassword: "newPass456!",
    });
  });

  it("throws when updatePassword throws", async () => {
    const error = new Error("NotAuthorizedException");
    vi.mocked(updatePassword).mockRejectedValueOnce(error);

    await expect(changePassword("oldPass123!", "newPass456!")).rejects.toThrow(
      "NotAuthorizedException"
    );
  });
});
