I want a project, that is capable of tracking changes in constants or preferably in given any language structure.

So, we have a "microservice" architechture, with mainly python and java services. 

Problem is: different services are developed by different teams. Services are somewhat dependent on each other, and there are some "indirect" dependencies.

As an example:

In some java service, there is a model called "Address", and it has for example, limit for street set as 100 symbols. This Address.street is exposed through CRUD API with this restriction.

Another python service is consuming Address.street through a rabbitmq message broker and saves it in its DB.

Then requirement change and address now should be increased to 120 symbols. This is formulated as task for Java team. Python team ideally should also know about this change, but on communication level it is not guaranteed.

I want to be able, as Python service dev -- to have an interface and be able to subscribe, ideally to any "language" structure, or at least to a given type, for exapmple, dict in python, Pydantic class, namedtuple etc. I want to recieve some sort of notification, if this structure changes. So, in our example, I want to subscribe to a constant (Address.street length) and be notified, when it is changed.



For now, focus on POC of this.

As POC, I want following:
* Analyzes diff of MR, is able to tell, if any subscription match for this diff.
* I want it to be done as "static" analysis, so no runtime of services is required to subscribe.
* As POC, it would be OK to subscribe to specific "lines" of code. But it should correctly update subscription on commit, if those lines are moved to other lines, or file is renamed.


I see this as following. As POC create a script, that:
* has access to codebase (path to folder for example)
* Has some ability to set subscriptions (maybe local file)
* Can do a "initial analysis" of codebase if needed, before changes, and save them locally
* Is able to tell from git diff of codebase (and codebase) if subscription should be triggered

We will be working in steps. For now focus on "line" management, but be aware of final scenario, so maybe create some abstractions for it if needed

Right now I want to subscribe to a "lines" of code and see, if subscription should be triggered. If "subscribed" lines are not changed, but there are additions, that alter "line numbers" -- "changes to subscription" document should be created. If applied, it is assumed, that "logic" of subscription is the same, after "unrelated" changes to codebase are applied.
