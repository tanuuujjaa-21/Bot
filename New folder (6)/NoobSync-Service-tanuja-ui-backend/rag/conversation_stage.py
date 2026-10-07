def detect_stage(message):
    message = message.lower()

    ready_keywords = [
        "enroll", "register", "buy", "purchase",
        "pay", "payment", "sign up", "book", "join"
    ]

    high_intent_keywords = [
        "price", "pricing","fee", "cost", "discount",
        "availability", "available", "batch",
        "schedule", "timing", "when", "demo"
    ]

    interested_keywords = [
        "details", "feature", "features",
        "benefits", "support", "course",
        "service", "services", "syllabus",
        "explain", "tell me more"
    ]

    # Ready
    for word in ready_keywords:
        if word in message:
            return "ready"

    # High Intent
    for word in high_intent_keywords:
        if word in message:
            return "high_intent"

    # Interested
    for word in interested_keywords:
        if word in message:
            return "interested"

    # Default
    return "browsing"


if __name__ == "__main__":
    print("Conversation Stage Detection")
    print("Type 'exit' to quit.\n")

    while True:
        user_message = input("User: ")

        if user_message.lower() == "exit":
            print("Program ended.")
            break

        stage = detect_stage(user_message)
        print("Stage:", stage)
        print()
