import {
  fetchUserAttributes,
  updateUserAttributes,
  confirmUserAttribute,
} from "aws-amplify/auth";

export interface UserProfileAttributes {
  email: string;
  given_name: string;
  family_name: string;
}

export interface ProfileUpdateResult {
  isUpdated: boolean;
  nextStep?: {
    updateAttributeStep: string;
    codeDeliveryDetails?: {
      attributeName: string;
      deliveryMedium: string;
      destination: string;
    };
  };
}

export async function loadProfileAttributes(): Promise<UserProfileAttributes> {
  const attributes = await fetchUserAttributes();
  return {
    email: attributes.email || "",
    given_name: attributes.given_name || "",
    family_name: attributes.family_name || "",
  };
}

export async function saveProfileAttributes(
  attributes: Partial<UserProfileAttributes>
): Promise<ProfileUpdateResult> {
  const updatePayload: Record<string, string> = {};
  
  if (attributes.email) {
    updatePayload.email = attributes.email;
  }
  
  if (attributes.given_name !== undefined) {
    updatePayload.given_name = attributes.given_name;
  }
  
  if (attributes.family_name !== undefined) {
    updatePayload.family_name = attributes.family_name;
  }

  const result = await updateUserAttributes({
    userAttributes: updatePayload,
  });

  if (result.email && result.email.nextStep.updateAttributeStep === "CONFIRM_ATTRIBUTE_WITH_CODE") {
    return {
      isUpdated: result.email.isUpdated,
      nextStep: {
        updateAttributeStep: result.email.nextStep.updateAttributeStep,
        codeDeliveryDetails: result.email.nextStep.codeDeliveryDetails
          ? {
              attributeName: "email",
              deliveryMedium: result.email.nextStep.codeDeliveryDetails.deliveryMedium || "EMAIL",
              destination: result.email.nextStep.codeDeliveryDetails.destination || "",
            }
          : undefined,
      },
    };
  }

  const isFullyUpdated = Object.values(result).every((attr) => attr.isUpdated);

  return {
    isUpdated: isFullyUpdated,
  };
}

export async function verifyEmailAttribute(code: string): Promise<void> {
  await confirmUserAttribute({
    userAttributeKey: "email",
    confirmationCode: code,
  });
}
