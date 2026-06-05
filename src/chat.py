from src.agent import ask_agent


def start_chat(context):
    print("Aksjeagent klar.")
    print("Skriv spørsmål, eller 'exit' for å avslutte.\n")

    while True:
        question = input("Du: ")

        if question.lower() in ["exit", "quit", "avslutt"]:
            print("Avslutter.")
            break

        answer = ask_agent(question, context)

        print("\nAgent:")
        print(answer)
        print("-" * 60)