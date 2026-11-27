
def make_config(data, user):
    config = {
        "configurable": {
            # The authenticated UUID scopes every checkpoint lookup/write.
            # Never use a client-provided thread ID as a global storage key.
            "thread_id": f"{user.id}:{data.thread_id}",
            "user_id": str(user.id)
        },
    }


    if data.title:
        config["metadata"] = {
            "title": data.title
        }

    return config